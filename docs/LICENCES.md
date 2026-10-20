# Licences

The Xenoform code is MIT. See [LICENSE](../LICENSE).

Weights, fonts, and pictures are separate. This page lists only licences checked against the upstream texts. Where a licence was not checked, it says so. Do not treat a missing row as permission.

The desk badge says **Open weights** and links to this page. That phrase does not mean every weight is an unrestricted open grant.

- **LTX-2.3** is under the LTX-2 Community License Agreement dated 5 January 2026. It applies to LTX-2 versions from that date, including LTX-2.3, until 11 August 2026. Free commercial use is allowed under about $10M annual revenue. Above that threshold, a paid licence is required.
- **LTX-2.5** is under the LTX-2.x Community License Agreement dated 11 August 2026. It applies to LTX-2.5 versions released since that date. The weights are open and run locally. Free commercial use is allowed under $10,000,000 annual revenue. At or above that, a paid Commercial Use Agreement is required. The desk graphs do not use an LTX partner node.
- **FLUX.2 Klein 9B and 9B Base** are under the FLUX Non-Commercial License. They are not the default, and they are not Apache 2.0.
- The desk's optional Klein file is the **Apache 2.0 4B**, `flux-2-klein-4b-fp8.safetensors`. Setup names that file and does not download the 9B weights.

Picture credits, including every unverified still and clip, are in [CREDITS.md](../CREDITS.md). The desk serves that file at `/credits`.

## Code

| Thing | Licence |
| --- | --- |
| This repository | MIT. [LICENSE](../LICENSE) |

## Models the desk can load

| Model | Where it is named | Licence checked |
| --- | --- | --- |
| LTX-Video 2B 0.9.5 | `checkpoints/ltx-video-2b-v0.9.5.safetensors` | Lightricks Open RAIL-M, 5 March 2025. [Licence text](https://huggingface.co/Lightricks/LTX-Video/blob/main/ltx-video-2b-v0.9.5.license.txt) |
| LTX-2.3 | `checkpoints/ltx-2.3-22b-distilled.safetensors` | LTX-2 Community License Agreement, 5 January 2026. It applies to LTX-2 versions from that date, including LTX-2.3, until 11 August 2026. Free commercial use under about $10M annual revenue. Above that, a paid licence. [Licence](https://github.com/Lightricks/LTX-2/blob/main/LICENSE) |
| LTX-2.5 | `diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | LTX-2.x Community License Agreement, 11 August 2026. Open weights, local graphs, not partner nodes. Free commercial use under $10,000,000 annual revenue. Above that, a paid licence. Layout IC-LoRA: `ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors`. [Licence](https://github.com/Lightricks/LTX-2/blob/main/LICENSE-2_x) |
| Z-Image Turbo | `diffusion_models/z_image_turbo_bf16.safetensors` | Tongyi-MAI / Alibaba, Apache 2.0. [Z-Image](https://github.com/Tongyi-MAI/Z-Image) |
| Z-Image text encoder | `text_encoders/qwen_3_4b_fp8_mixed.safetensors` | Qwen3-4B, Alibaba Cloud, Apache 2.0, modified by Tongyi. Same Z-Image pack. |
| Z-Image VAE | `vae/ae.safetensors` | FLUX.1 autoencoder, Black Forest Labs, Apache 2.0. It ships in the Z-Image Comfy pack. |
| FLUX.2 Klein 4B | `diffusion_models/flux-2-klein-4b-fp8.safetensors` | Apache 2.0. This is the file the desk names. [FLUX.2](https://github.com/black-forest-labs/flux2) |
| FLUX.2 Klein 9B and 9B Base | Not a desk download | FLUX Non-Commercial License. Do not describe the 9B weights as Apache 2.0. |
| FLUX.3 Klein | Optional local file, not downloaded by setup | Licence not checked in this audit. Do not assume one. |
| T5-XXL fp8 | `text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors` | Licence not checked in this audit. The file comes from `comfyanonymous/flux_text_encoders`. |
| ACE-Step 1.5 | `checkpoints/ace_step_1.5_turbo_aio.safetensors` | MIT, per the ACE-Step/Ace-Step1.5 model card (checked 19 October 2026). Optional. The bundled demo track does not need it. [Model card](https://huggingface.co/ACE-Step/Ace-Step1.5) |
| Real-ESRGAN x4plus (Xintao Wang) | `upscale_models/RealESRGAN_x4plus.pth` | BSD-3-Clause, per the [Real-ESRGAN LICENSE](https://github.com/xinntao/Real-ESRGAN/blob/master/LICENSE) (checked 20 October 2026): commercial use allowed, keep the copyright notice. **Default** Final-tier upscale. Weights: [v0.1.0 release](https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth). |
| 4xNomos8kSC (Helaman) | `upscale_models/4xNomos8kSC.pth` | CC-BY-4.0, per [OpenModelDB](https://openmodeldb.info/models/4x-Nomos8kSC) (checked 20 October 2026): commercial use allowed, credit required. Tested as an alternative (peaked 11.8 GB of 12); not the default. |
| 4x-ClearReality V1 (Kim2091) | `upscale_models/4x-ClearRealityV1.safetensors` | CC BY-NC-SA 4.0, per OpenModelDB (checked 19 October 2026): non-commercial, credit required, share alike. **Opt-in only** since 20 October 2026: `XENO_FINAL_UPSCALER=4x-ClearRealityV1.safetensors`. `XENO_FINAL_UPSCALE=0` skips the upscale. [OpenModelDB](https://openmodeldb.info/models/4x-ClearRealityV1) |
| LTX-2.3 spatial upscaler x2 1.1 | `latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors` | Licence not checked in this audit. Ships with LTX-2.3; used by the Final tier. |
| Gemma 3 12B text encoder (fp4) | `text_encoders/gemma_3_12B_it_fp4_mixed.safetensors` | Licence not checked in this audit. Used by LTX-2.3. |
| Wan 2.2 TI2V 5B | Optional diffusion, VAE, and text encoder | Licence not checked in this audit. Optional. Turbo never loads it. |

## Fonts shipped in the desk

Both families are SIL Open Font License 1.1. The copyright lines and the licence text are in [src/xenoform/ui_static/fonts/OFL.txt](../src/xenoform/ui_static/fonts/OFL.txt).

| Font | Files | Copyright |
| --- | --- | --- |
| Space Grotesk | `space-grotesk-400.woff2`, `space-grotesk-500.woff2`, `space-grotesk-600.woff2`, `space-grotesk-700.woff2` | Copyright 2020 The Space Grotesk Project Authors |
| Share Tech Mono | `share-tech-mono-400.woff2` | Copyright (c) 2012, Carrois Type Design, Ralph du Carrois, with Reserved Font Name 'Share' |

## Pictures and sound in the repo

| Asset | Status |
| --- | --- |
| `examples/demo.wav` | Synthesized by `xenoform synth`. No third-party recording. |
| Contest demo video track ("Morphing Wobble") | Not in the repo. Made with Suno. Usage rights follow the Suno plan it was made on; to be confirmed by the author before release. |
| Vibe stills and library clips | No author or licence metadata in the files. Each one is TODO in [CREDITS.md](../CREDITS.md). No CC BY credit was added. |
| `workflows/xenoform_draft.json`, `workflows/xenoform_final.json`, `workflows/xenoform_morph.json`, `workflows/ltx_v2v_api.json`, `workflows/ltx_v2v_guide_api.json`, `workflows/ltx25_a2v_api.json`, `workflows/ltx25_multishot_api.json`, `workflows/ltx25_layout_api.json` | Part of this MIT repository. The weight files they name are not. |

`COMFY_API_KEY` stays in the environment. It is not written into the repo.
