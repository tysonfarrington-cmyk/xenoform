# Open on the drop

Judges decide in the first seconds. The claim of this desk is that the song chooses the object, and the morph lands on the downbeat. Waiting for a GPU render hides that claim.

The Simple desk therefore opens with one card, before any checkpoint loads:

- the first drop in the song
- the source and the target the score picked for it
- one sentence that says why
- **Play the drop**, which seeks the audio to that downbeat and flashes the card once

The flash is a class toggle for 80 milliseconds. There is no CSS animation and no shimmer. The time comes from the same downbeat grid the morph engine uses: every fourth detected beat, then the downbeat nearest the drop.

Open weights stay on the local path. The card names items from the sample library on this machine. It does not call a partner API and it does not show a face.
