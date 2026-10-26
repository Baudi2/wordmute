# /brag-slim plan — WordMute

**Input:** the project at C:\wordmute-app (its site docs/index.html, README.md, the real UI renders in docs/design). Tone `default`, landscape 1920×1080 @ 30 fps, ~20.7 s. Language: Russian (the audience).

## What is it
WordMute — a Windows app that finds unwanted words in a video's audio with local speech recognition and mutes exactly those words, leaving the video and the rest of the sound untouched. Fully on the user's PC.

- **Who / what for:** Russian-speaking viewers who want films, series and online videos without certain words — word by word, not whole sentences.
- **What sets it apart:** word-precision muting; everything local (files never leave the PC); download by link (YouTube, VK Видео, RUTUBE, Boosty); a review screen where each muted word can be heard and un-muted in one click; GigaAM for Russian; NVIDIA GPU speed-up; free.
- **Most impressive claim:** «Нежелательные слова в видео — под заглушкой» — one word drops out, everything else stays.
- **Visual hook:** the site's signature wave: amber speech bars, and the muted word collapsing into a flat red segment.
- **Real UI shown:** the queue (cards: done / processing / downloading / queued), the Review window (table + waveform strip, a checkbox un-muting a false positive), the Add-URL dialog with the format table, the "done" toast.
- **Share caption:** see share-copy.txt.

## Identity
Site palette: bg #14161a, panel #1b1e24, line #2a2e36, text #e9e7e2, dim #9096a0, amber #e8a33d, mute #e5484d, accent-soft rgba(232,163,61,.12). Fonts on the machine: Inter (bundled with the app — the app's own UI font; stands in for the site's Space Grotesk headlines) and Consolas for mono labels. Logo mark: amber rounded square with four dark bars (from the site's SVG).

## Music & sound
`happy-beats-business-moves-vol-11` by Sascha Ende, ende.app (CC BY 4.0 — credit on the site and in the share copy). 114.84 BPM, beat 0.5225 s. Every cut lands on its beat grid; the strong cues 1.60 / 3.70 / 6.34 / 9.50 / 12.65 / 17.91 are the scene cuts. SFX (Kenney, CC0): `interface/switch_006` on the mute, `impact/impactSoft_medium_001` on the title, `interface/click_003` on chips and the simulated click, `casino/card-slide-1` on the panels sliding in, `interface/drop_002` on the toast, `impact/impactBell_heavy_003` on the outro. Effects sit under the music; music fades over the last 1.3 s.

## Storyboard (20.7 s)
| # | Time | Scene | Motion | Sound |
|---|---|---|---|---|
| 1 | 0.00–3.70 | **Hook.** The wave plays with a playhead; a subtitle line («…дальше по сюжету появляется [слово], и герой уходит…») lights up word by word under it. At 1.60 the playhead reaches the word: its bars collapse to flat red, the word is struck through, tag «заглушено». | playhead sweep; bars collapse in 0.2 s; tag pops | switch at 1.60 |
| 2 | 3.70–6.34 | **Reveal.** Logo mark + «WordMute» land; 4.23 tagline «Нежелательные слова в видео — под заглушкой»; 5.28 eyebrow «Windows · локальная обработка · бесплатно». | scale-in + rise; dip to bg before | impact at 3.70 |
| 3 | 6.34–9.50 | **Queue.** The real main window slides up; three chips appear on beats: «распознаёт речь» 6.34, «находит слова из вашего списка» 6.86, «глушит только их» 7.38; slow zoom on the cards; at 8.44 the «Готово: 3 файла · заглушено 37 слов» toast drops in. | slide-up, chips pop, Ken Burns | card-slide, 3 clicks, drop |
| 4 | 9.50–12.65 | **Review.** The real Review window; label «Каждое заглушенное слово можно прослушать — и вернуть одним кликом». Cursor glides to row 2 («обожаю») 10.54–11.06, clicks: checkbox clears, counts line updates. | slide-in, cursor path, state swap | card-slide, click at 11.06 |
| 5a | 12.65–15.28 | **By link.** Add-URL dialog with the format table; chips YouTube · VK Видео · RUTUBE · Boosty appear on beats. Label «Вставьте ссылку — скачает и обработает». | slide-in, chips | card-slide, clicks |
| 5b | 15.28–17.91 | **Local.** Big line «Всё на вашем компьютере.» + «Файлы никуда не отправляются» + «с NVIDIA — в разы быстрее». | lines rise in on beats | — |
| 6 | 17.91–20.70 | **Outro.** Logo + «WordMute», «Скачать для Windows — бесплатно», mono URL baudi2.github.io/wordmute. Settled from 18.6 s. | land + hold | bell at 17.91, music fade |

Transitions: dip through the background (6–8 frames), never a crossfade of two busy layouts. Text that must be read stays ≥ 0.3 s/word after it settles.

**Poster:** the settled Reveal frame (≈5.9 s): logo, tagline, eyebrow.
