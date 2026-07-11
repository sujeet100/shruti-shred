# Soundfonts

The renderer needs `MuseScore_General.sf3` here (Distortion Guitar = GM program 30).
It's a ~38MB binary, kept out of git — download it once:

```
curl -L -o soundfonts/MuseScore_General.sf3 \
  https://ftp.osuosl.org/pub/musescore/soundfont/MuseScore_General/MuseScore_General.sf3
```

Source: MuseScore's default General MIDI soundfont (MuseScore handbook →
"Soundfonts and SFZ files"). FluidSynth itself is a **system** binary — install
via `brew install fluidsynth`, not pip.
