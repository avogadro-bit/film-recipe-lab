"""Local photographic studio with an independent RAW renderer."""
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import errno
from pathlib import Path
import secrets
import hashlib
import tempfile
import threading
import webbrowser
import zipfile
from typing import Literal
from urllib.parse import urlparse, parse_qs

from PIL import Image, ImageOps
import numpy as np
import rawpy

from .input_profiles import RAW_EXTENSIONS
from .engine import status
from .lut_install import install_archive
from .raw import local_file, exif
from .studio import StudioRecipe as Recipe, studio_status, decode, render, encode, shooting_settings
from pydantic import BaseModel, ConfigDict, Field, StrictBool


class RenderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    recipe: Recipe
    neutral: StrictBool = False
    quality: Literal['interactive','full'] = 'full'


class TileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    recipe: Recipe
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    size: int = Field(default=512, ge=128, le=1024)
    level: Literal[1,2,4,8] = 1


class BatchExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[RenderRequest] = Field(min_length=2, max_length=100)

STATIC = Path(__file__).with_name("static")
MAX_UPLOAD = 200*1024*1024
MAX_LUT_ARCHIVE = 160*1024*1024
MAX_BATCH_REQUEST = 512*1024


def output_geometry(shape, recipe):
    """Map the developed RAW into the recipe's final output coordinates."""
    h,w=shape[:2]
    cw,ch=int(w/recipe.digital_crop),int(h/recipe.digital_crop)
    if recipe.aspect!='original':
        rw,rh=map(int,recipe.aspect.split(':'));ratio=rw/rh
        if h>w:ratio=1/ratio
        if cw/ch>ratio:cw=round(ch*ratio)
        else:ch=round(cw/ratio)
    left,top=(w-cw)//2,(h-ch)//2
    factor={'L':1.,'M':.7071,'S':.5}[recipe.image_size]
    edge=round(max(cw,ch)*factor)
    if edge>=max(cw,ch):out_w,out_h=cw,ch
    else:out_w,out_h=max(1,round(cw*edge/max(cw,ch))),max(1,round(ch*edge/max(cw,ch)))
    return {'source':(left,top,cw,ch),'output':(out_w,out_h),'full':(w,h)}


def downsample_box(pixels, factor):
    """Memory-bounded area reduction for lower-resolution viewport levels."""
    if factor==1:return pixels
    h,w=pixels.shape[:2];out_h=(h+factor-1)//factor;out_w=(w+factor-1)//factor
    result=np.zeros((out_h,out_w,3),np.float32);counts=np.zeros((out_h,out_w),np.float32)
    for yy in range(factor):
        for xx in range(factor):
            sample=pixels[yy::factor,xx::factor]
            if not sample.size:continue
            sh,sw=sample.shape[:2];result[:sh,:sw]+=sample;counts[:sh,:sw]+=1
    result/=np.maximum(counts[:,:,None],1)
    return result


class Library:
    def __init__(self, roots, scratch):
        self.files = {}
        self.roots = [Path(p).expanduser().resolve() for p in roots] or [Path.home()]
        self.scratch = Path(scratch)
        self.previews = OrderedDict()
        self.thumbnails = OrderedDict()
        self.details = {}
        self.linear_cache = OrderedDict()
        self.corrected_cache = OrderedDict()
        self.tile_cache = OrderedDict()
        self.lock = threading.RLock()
        self.decoder_lock = threading.Semaphore(1)
        self.full_render_lock = threading.Semaphore(1)
        self.tile_render_lock = threading.Semaphore(2)
        for root in self.roots:
            if not root.is_dir():
                raise ValueError(f"Folder not found: {root}")
            # Folder shortcuts only. Scan after explicit selection in the GUI.

    def folders(self, path=None):
        folder = Path(path).expanduser().resolve() if path else self.roots[0]
        if not folder.is_dir():
            raise ValueError("Folder not found.")
        # Authenticated local picker: paths are explicitly selected by the user.
        children = []
        raw_count = 0
        for p in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
            if not p.name.startswith('.') and p.is_dir():
                children.append({"name":p.name,"path":str(p.resolve())})
            elif p.is_file() and p.suffix.lower() in RAW_EXTENSIONS:
                raw_count += 1

        home = Path.home().resolve()
        shortcut_candidates = [
            ("Home", home),
            ("Desktop", home / "Desktop"),
            ("Pictures", home / "Pictures"),
            ("Documents", home / "Documents"),
            ("Downloads", home / "Downloads"),
            *[("Start Folder" if root == home else root.name or str(root), root) for root in self.roots],
        ]
        shortcuts, seen = [], set()
        for name, candidate in shortcut_candidates:
            candidate = candidate.resolve()
            if candidate.is_dir() and candidate not in seen:
                shortcuts.append({"name": name, "path": str(candidate)})
                seen.add(candidate)

        if folder == home or folder.is_relative_to(home):
            breadcrumbs = [{"name": "Home", "path": str(home)}]
            cursor = home
            if folder != home:
                for part in folder.relative_to(home).parts:
                    cursor /= part
                    breadcrumbs.append({"name": part, "path": str(cursor)})
        else:
            anchor = Path(folder.anchor)
            breadcrumbs = [{"name": folder.anchor or "/", "path": str(anchor)}]
            cursor = anchor
            for part in folder.parts[1:]:
                cursor /= part
                breadcrumbs.append({"name": part, "path": str(cursor)})

        return {
            "path": str(folder),
            "name": folder.name or str(folder),
            "parent": str(folder.parent) if folder.parent != folder else None,
            "folders": children,
            "shortcuts": shortcuts,
            "breadcrumbs": breadcrumbs,
            "raw_count": raw_count,
        }

    def select_folder(self, path, recursive=True):
        folder=Path(path).expanduser().resolve()
        if not folder.is_dir():raise ValueError("Folder not found.")
        iterator=folder.rglob('*') if recursive else folder.iterdir()
        selected=[]
        for p in sorted(iterator):
            if p.suffix.lower() in RAW_EXTENSIONS and p.is_file():
                selected.append(self.add(p,folder.name))
                if len(selected)>=5000:break
        return {"folder":str(folder),"files":selected,"limit_reached":len(selected)>=5000}

    def add(self, path, group="Imports"):
        path = path.resolve()
        st = path.stat()
        identifier = hashlib.sha256(f"{path}:{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest()[:24]
        with self.lock:
            self.files[identifier] = {"id": identifier, "name": path.name, "path": str(path),
                                      "format": path.suffix[1:].upper(), "bytes": st.st_size,
                                      "local": local_file(path), "group": group}
            return self.files[identifier]

    def listing(self):
        with self.lock:
            return list(self.files.values())

    def inspect(self, identifier):
        with self.decoder_lock:
            if identifier in self.details and (not self.details[identifier]["preview_available"] or identifier in self.previews):
                if identifier in self.previews:
                    self.previews.move_to_end(identifier)
                return self.details[identifier]
            with self.lock:
                item = self.files[identifier]
            # Recheck immediately before reading: iCloud residency can change
            # while the library remains open.
            if not local_file(Path(item["path"])):
                raise ValueError("This iCloud file must be downloaded in Finder before it can be opened.")
            path = Path(item["path"])
            info = {**item, "exif": exif(path), "preview_available": False,
                    "preview_kind": "embedded", "recipe_applied": False, "exact_fuji_render": False}
            with rawpy.imread(str(path)) as raw:
                info["sizes"] = raw.sizes._asdict()
                width,height=raw.sizes.width,raw.sizes.height
                if raw.sizes.flip in (5,6):width,height=height,width
                info["developed_size"]={"width":width,"height":height}
                try:
                    thumb = raw.extract_thumb()
                    picture = Image.open(BytesIO(thumb.data)) if thumb.format == rawpy.ThumbFormat.JPEG else Image.fromarray(thumb.data)
                    picture = ImageOps.exif_transpose(picture)
                    picture.thumbnail((1800, 1400), Image.Resampling.LANCZOS)
                    output = BytesIO()
                    picture.convert("RGB").save(output, format="JPEG", quality=90, icc_profile=picture.info.get("icc_profile"))
                    self.previews[identifier] = output.getvalue()
                    while len(self.previews) > 32:
                        self.previews.popitem(last=False)
                    info["preview_available"] = True
                    info["preview_size"] = list(picture.size)
                except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                    info["preview_reason"] = "This file has no readable embedded preview."
            from .studio import source_details
            info["source_exposure"] = source_details(path)
            info["input_normalization"] = info["source_exposure"].get("normalization",{})
            info["shooting_settings"] = shooting_settings(info["exif"])
            from .optics import inspect_optics
            try:
                info["optics"] = inspect_optics(path)
            except (OSError, ValueError, RuntimeError) as exc:
                info["optics"] = {"distortion":False,"vignetting":False,"label":f"Lens profile unavailable: {exc}"}
            self.details[identifier] = info
            return info

    def thumbnail(self, identifier):
        """Return a small embedded RAW preview without running the render pipeline."""
        with self.decoder_lock:
            if identifier in self.thumbnails:
                self.thumbnails.move_to_end(identifier)
                return self.thumbnails[identifier]
            with self.lock:
                item = self.files[identifier]
            path = Path(item["path"])
            if not local_file(path):
                raise ValueError("This iCloud file must be downloaded before its thumbnail can be shown.")
            try:
                if identifier in self.previews:
                    picture = Image.open(BytesIO(self.previews[identifier]))
                else:
                    with rawpy.imread(str(path)) as raw:
                        thumb = raw.extract_thumb()
                        picture = (Image.open(BytesIO(thumb.data)) if thumb.format == rawpy.ThumbFormat.JPEG
                                   else Image.fromarray(thumb.data))
                picture = ImageOps.exif_transpose(picture)
                picture.thumbnail((360, 240), Image.Resampling.LANCZOS)
                output = BytesIO()
                picture.convert("RGB").save(output, format="JPEG", quality=84,
                                            icc_profile=picture.info.get("icc_profile"))
            except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                raise ValueError("This RAW file has no embedded thumbnail.") from None
            self.thumbnails[identifier] = output.getvalue()
            while len(self.thumbnails) > 96:
                self.thumbnails.popitem(last=False)
            return self.thumbnails[identifier]


    def develop(self, request, export=False):
        with self.lock:
            item = self.files[request.id]
        path = Path(item["path"])
        if not local_file(path):
            raise ValueError("The iCloud file is not downloaded. Open Finder to download it.")

        def finish(linear):
            if request.recipe.lens_distortion != 'off' or request.recipe.lens_vignetting != 'off':
                from .optics import inspect_optics, apply_corrections
                linear=apply_corrections(linear,inspect_optics(path),
                                         request.recipe.lens_distortion,request.recipe.lens_vignetting)
            pixels = render(linear, request.recipe, neutral=request.neutral)
            return encode(pixels, request.recipe, preview=not export)

        if not export and request.quality == 'interactive':
            # Serialize only LibRaw access, not the small render. An interactive
            # edit can therefore overtake an obsolete 60 MP refinement.
            with self.decoder_lock:
                linear = decode(path, preview=True)
            return finish(linear)

        # Full exports remain serialized to bound peak memory. Release the RAW
        # decoder as soon as its result is cached so reduced previews can render
        # concurrently with the expensive full-size effects pipeline.
        with self.full_render_lock:
            with self.decoder_lock:
                if request.id not in self.linear_cache:
                    # Reuse this full-size development for the stabilized
                    # preview and export. Keep only the active photo to bound
                    # the roughly 700 MB float32 working set of a 60 MP RAW.
                    self.linear_cache[request.id] = decode(path, preview=False)
                    while len(self.linear_cache) > 1:
                        self.linear_cache.popitem(last=False)
                self.linear_cache.move_to_end(request.id)
                linear = self.linear_cache[request.id]
            return finish(linear)

    def full_linear(self, identifier):
        """Decode once; viewport tiles and export share the active RAW buffer."""
        with self.lock:
            item=self.files[identifier]
        path=Path(item['path'])
        if not local_file(path):
            raise ValueError("The iCloud file is not downloaded. Open Finder to download it.")
        with self.decoder_lock:
            if identifier not in self.linear_cache:
                self.linear_cache[identifier]=decode(path,preview=False)
                while len(self.linear_cache)>1:self.linear_cache.popitem(last=False)
            self.linear_cache.move_to_end(identifier)
            return self.linear_cache[identifier]

    def render_tile(self, request):
        """Render one source-resolution viewport tile, never a giant browser JPEG."""
        recipe_key=hashlib.sha256(request.recipe.model_dump_json().encode()).hexdigest()[:20]
        cache_key=(request.id,recipe_key,request.x,request.y,request.size,request.level)
        with self.lock:
            if cache_key in self.tile_cache:
                self.tile_cache.move_to_end(cache_key)
                return self.tile_cache[cache_key]
            item=self.files[request.id]
        path=Path(item['path']);linear=self.full_linear(request.id)
        optics_key=(request.id,request.recipe.lens_distortion,request.recipe.lens_vignetting)
        if request.recipe.lens_distortion!='off' or request.recipe.lens_vignetting!='off':
            with self.full_render_lock:
                with self.lock:corrected=self.corrected_cache.get(optics_key)
                if corrected is None:
                    from .optics import inspect_optics, apply_corrections
                    corrected=apply_corrections(linear,inspect_optics(path),
                        request.recipe.lens_distortion,request.recipe.lens_vignetting)
                    with self.lock:
                        self.corrected_cache[optics_key]=corrected
                        while len(self.corrected_cache)>1:self.corrected_cache.popitem(last=False)
            linear=corrected
        geometry=output_geometry(linear.shape,request.recipe)
        left,top,crop_w,crop_h=geometry['source'];out_w,out_h=geometry['output']
        if request.x>=out_w or request.y>=out_h:raise ValueError('Tile lies outside the developed image.')
        span=request.size*request.level
        tile_w=min(span,out_w-request.x);tile_h=min(span,out_h-request.y)
        sx0=left+(request.x*crop_w)//out_w
        sy0=top+(request.y*crop_h)//out_h
        sx1=left+((request.x+tile_w)*crop_w+out_w-1)//out_w
        sy1=top+((request.y+tile_h)*crop_h+out_h-1)//out_h
        halo=256;level=request.level
        rx0=max(0,((sx0-halo)//level)*level);ry0=max(0,((sy0-halo)//level)*level)
        rx1=min(linear.shape[1],((sx1+halo+level-1)//level)*level)
        ry1=min(linear.shape[0],((sy1+halo+level-1)//level)*level)
        sample_step=max(1,max(linear.shape[:2])//640)
        context={'sample':linear[::sample_step,::sample_step],
                 'full_shape':((linear.shape[0]+level-1)//level,
                               (linear.shape[1]+level-1)//level,3)}
        region=downsample_box(linear[ry0:ry1,rx0:rx1],level)
        with self.tile_render_lock:
            pixels=render(region,request.recipe,output_transform=False,context=context,
                          origin=(ry0//level,rx0//level))
        crop_x0=(sx0-rx0)//level;crop_y0=(sy0-ry0)//level
        crop_x1=(sx1-rx0+level-1)//level;crop_y1=(sy1-ry0+level-1)//level
        pixels=pixels[crop_y0:crop_y1,crop_x0:crop_x1]
        target_w=max(1,(tile_w+request.level-1)//request.level)
        target_h=max(1,(tile_h+request.level-1)//request.level)
        if pixels.shape[1]!=target_w or pixels.shape[0]!=target_h:
            pixels=np.stack([np.asarray(Image.fromarray(pixels[:,:,channel]).resize(
                (target_w,target_h),Image.Resampling.LANCZOS)) for channel in range(3)],axis=-1)
        data,mime=encode(pixels,request.recipe,preview=True)
        result=(data,mime)
        with self.lock:
            self.tile_cache[cache_key]=result
            while len(self.tile_cache)>96:self.tile_cache.popitem(last=False)
        return result

    def export_jpeg_archive(self, requests):
        """Render each requested photo with its own recipe into a temporary ZIP."""
        identifiers = [request.id for request in requests]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Each photo may appear only once in a batch export.")
        if any(request.recipe.file_type != "jpeg" for request in requests):
            raise ValueError("Batch export supports JPEG output only.")
        with self.lock:
            missing = [identifier for identifier in identifiers if identifier not in self.files]
        if missing:
            raise ValueError("One or more selected photos are no longer in the library.")

        archive_path = self.scratch/f"film-recipe-lab-{secrets.token_hex(12)}.zip"
        used_names = set()
        try:
            with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_STORED) as archive:
                for index, request in enumerate(requests, 1):
                    data, mime = self.develop(request, export=True)
                    if mime != "image/jpeg":
                        raise ValueError("Batch export produced a non-JPEG image.")
                    with self.lock:
                        source_name = self.files[request.id]["name"]
                    stem = "".join(character if character.isalnum() or character in "-_ ." else "_"
                                   for character in Path(source_name).stem).strip(" .") or f"photo-{index}"
                    candidate = f"{stem}-{request.recipe.film}.jpg"
                    suffix = 2
                    while candidate.casefold() in used_names:
                        candidate = f"{stem}-{request.recipe.film}-{suffix}.jpg"
                        suffix += 1
                    used_names.add(candidate.casefold())
                    archive.writestr(candidate, data)
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
        return archive_path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # No file paths, session tokens or recipe contents in HTTP logs.

    def send(self, code, data, content_type="application/json; charset=utf-8"):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # The browser may abort an obsolete image request.

    def send_file(self, path, content_type, download_name):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(1024*1024):
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized(self):
        host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != host or self.headers.get("Origin", f"http://{host}") != f"http://{host}":
            self.send(403, {"error": "Unauthorized origin"})
            return False
        if not secrets.compare_digest(self.headers.get("X-Fuji-Session", ""), self.server.session_token):
            self.send(403, {"error": "Session expired. Reopen the link displayed at launch."})
            return False
        return True

    def do_GET(self):
        route = urlparse(self.path).path
        static = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
        if route in static:
            filename, mime = static[route]
            return self.send(200, (STATIC/filename).read_bytes(), mime)
        if not self.authorized():
            return
        try:
            if route == "/api/folders":
                return self.send(200,self.server.library.folders(parse_qs(urlparse(self.path).query).get("path",[None])[0]))
            if route == "/api/library":
                return self.send(200, {"files": self.server.library.listing(), "engine": studio_status(), "native_engine": status(), "recipe": Recipe().model_dump()})
            if route.startswith("/api/photo/"):
                return self.send(200, self.server.library.inspect(route.split("/")[-1]))
            if route.startswith("/api/preview/"):
                identifier = route.split("/")[-1]
                self.server.library.inspect(identifier)
                return self.send(200, self.server.library.previews[identifier], "image/jpeg")
            if route.startswith("/api/thumbnail/"):
                identifier = route.split("/")[-1]
                return self.send(200, self.server.library.thumbnail(identifier), "image/jpeg")
            self.send(404, {"error": "Resource not found"})
        except KeyError:
            self.send(404, {"error": "Photo or preview not found"})
        except Exception as exc:
            self.send(422, {"error": str(exc)})

    def do_POST(self):
        if not self.authorized():
            return
        route = urlparse(self.path)
        try:
            self.connection.settimeout(60)
            length = int(self.headers.get("Content-Length", "0"))
            limit = (MAX_UPLOAD if route.path == "/api/import" else
                     MAX_LUT_ARCHIVE if route.path == "/api/luts/install" else
                     MAX_BATCH_REQUEST if route.path == "/api/export-batch" else 65536)
            if not 0 < length <= limit:
                maximum = ("200 MB" if route.path == "/api/import" else
                           "160 MB" if route.path == "/api/luts/install" else
                           "512 KB" if route.path == "/api/export-batch" else "64 KB")
                return self.send(413, {"error": f"File too large or empty request (maximum: {maximum})."})
            if route.path == "/api/import":
                name = Path(parse_qs(route.query).get("name", [""])[0]).name
                if Path(name).suffix.lower() not in RAW_EXTENSIONS:
                    return self.send(415, {"error": "Choose a compatible RAW: RAF, DNG, CR2/CR3, NEF, ARW, RW2, ORF…"})
                folder = self.server.library.scratch/secrets.token_hex(12)
                folder.mkdir()
                path = folder/name
                self.connection.settimeout(60)
                with path.open("xb") as stream:
                    remaining = length
                    while remaining:
                        chunk = self.rfile.read(min(1024*1024, remaining))
                        if not chunk:
                            raise ValueError("Import interrupted")
                        stream.write(chunk)
                        remaining -= len(chunk)
                return self.send(201, self.server.library.add(path))
            if route.path == "/api/luts/install":
                name = Path(parse_qs(route.query).get("name", [""])[0]).name
                if Path(name).suffix.lower() != ".zip":
                    return self.send(415, {"error": "Choose the GFX ETERNA 55 ZIP archive downloaded from Fujifilm."})
                path = self.server.library.scratch/f"luts-{secrets.token_hex(12)}.zip"
                try:
                    with path.open("xb") as stream:
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(1024*1024, remaining))
                            if not chunk:
                                raise ValueError("LUT archive upload interrupted")
                            stream.write(chunk)
                            remaining -= len(chunk)
                    install_archive(path)
                finally:
                    path.unlink(missing_ok=True)
                engine = studio_status()
                return self.send(201, {"installed": not engine["missing_luts"], "engine": engine})
            body = self.rfile.read(length)
            if route.path == "/api/folder":
                value=json.loads(body)
                if not isinstance(value,dict) or not isinstance(value.get("path"),str) or not value["path"].strip() or not isinstance(value.get("recursive",True),bool):
                    raise ValueError("Invalid folder selection.")
                return self.send(200,self.server.library.select_folder(value["path"],value.get("recursive",True)))
            if route.path == "/api/recipe":
                recipe = Recipe.model_validate_json(body)
                return self.send(200, {"recipe": recipe.model_dump(), "notes": recipe.unsupported(), "render_available": True})
            if route.path == "/api/tile":
                request = TileRequest.model_validate_json(body)
                data,mime = self.server.library.render_tile(request)
                return self.send(200,data,mime)
            if route.path in {"/api/render", "/api/export"}:
                request = RenderRequest.model_validate_json(body)
                data, mime = self.server.library.develop(request, export=route.path == "/api/export")
                return self.send(200, data, mime)
            if route.path == "/api/export-batch":
                request = BatchExportRequest.model_validate_json(body)
                self.connection.settimeout(3600)
                archive = self.server.library.export_jpeg_archive(request.items)
                try:
                    return self.send_file(archive, "application/zip", "film-recipe-lab-export.zip")
                finally:
                    archive.unlink(missing_ok=True)
            self.send(404, {"error": "Command not found"})
        except Exception as exc:
            self.send(422, {"error": str(exc)})


def bind_studio_server(port):
    try:
        return ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        # Let the OS select and reserve a free port atomically.
        return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


def serve(roots, port=8765, open_browser=False):
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be between 1024 and 65535")
    with tempfile.TemporaryDirectory(prefix="film-recipe-lab-") as scratch:
        server = bind_studio_server(port)
        server.daemon_threads = True
        server.session_token = secrets.token_urlsafe(32)
        server.library = Library(roots, scratch)
        session_url = f"http://127.0.0.1:{server.server_port}/#session={server.session_token}"
        if server.server_port != port:
            print(f"Port {port} is already in use. Opening on available port {server.server_port}.", flush=True)
        print(f"Film Recipe Lab : {session_url}", flush=True)
        print("Local service. Press Ctrl+C to quit. Temporary imports are removed at shutdown.", flush=True)
        if open_browser:
            # Defer browser launch until serve_forever has started accepting requests.
            launcher = threading.Timer(0.2, webbrowser.open, args=(session_url,), kwargs={"new": 2})
            launcher.daemon = True
            launcher.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
