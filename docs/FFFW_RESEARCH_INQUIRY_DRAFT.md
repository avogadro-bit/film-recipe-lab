# Demande technique — brouillon non envoyé

Destinataire envisagé : auteur de fffw ou communauté FujiHack.

Hello,

I am researching whether the native Fujifilm RAW processing pipeline can run on a computer without a connected camera. My initial target is X-T4 firmware 2.12. I have inspected the public fffw sources at commit bedc091e0b54a1a34aaf6929dd08e1db36d13b08.

Selected ARM functions run under Unicorn, but full image processing is not working. One initialization path stops at a read of MMIO address 0xff70f03c. The firmware uses a 16-entry address table at 0x1587714, covering 0xff70f000 through 0xff70f03c, and requests a read-modify-write clearing mask 0x7 at the last register. These addresses refer to our decoded module mapped at 0x01021000; they have not been verified against a live camera dump.

Do you have public documentation or research results identifying this peripheral, its reset state, and the relevant initialization sequence? Does the X-T4 service interface permit observing this region, and under what access restrictions?

I would also appreciate pointers to any publishable ffem peripheral models, synchronized traces, or RAW pipeline intermediate input/output captures for this model. I am trying to distinguish host-executed algorithms from operations delegated to image-processing hardware. A firmware-only emulator has not yet demonstrated an exact image result.

No firmware flashing or calibration modifications are requested. Existing documentation or captures would be the preferred starting point. Thank you.
