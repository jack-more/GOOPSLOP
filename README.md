# goopslop

Launch-week edge finder for the GTA VI prediction markets on Kalshi and Polymarket.

Most of these markets settle on public data that a script can read faster than a person can
refresh a page: the Metascore, the radio tracklist, Luminate's album numbers, Take-Two press
releases. The order books are thin and mostly priced by hand. goopslop reads the data, prices
every threshold, and flags the ones the market has wrong.

No dependencies beyond Python 3.10+.

## Commands

```sh
python -m goopslop board              # every open GTA VI market on both venues
python -m goopslop pairs              # same question on both venues, priced as a locked two-leg trade
python -m goopslop mc calibrate       # measure embargo-day -> day-7 Metascore drift on past launches
python -m goopslop mc watch           # poll Metacritic every 30s, flag mispriced thresholds
python -m goopslop mc watch --slug red-dead-redemption-2 --once   # dry run on a game with reviews
python -m goopslop discover           # full Kalshi scan for new GTA events (slow)
python -m unittest discover -s tests
```

## How the Metacritic watcher prices a threshold

1. Metacritic's backend returns `normalizedScore`, the unrounded number behind the displayed
   Metascore. A displayed 97 can be 96.5 or 97.4, and that difference decides the 97+ market.
2. `mc calibrate` measures how far the score moved between embargo day and day 7 on 11 past
   blockbusters. Rockstar launches barely moved (RDR2 +0.05, GTA V -0.11); broken launches did
   (Cyberpunk -4.5, Starfield -1.8). The median drift sets the bias, and the RMS of the
   scaled drift sets the noise, so those tails stay in the forecast.
3. The forecast is normal around `normalizedScore + bias`, with the bias shrinking as the
   remaining reviews come in. P(threshold) accounts for the display rounding.
4. Edge = fair probability minus the price you'd pay, after Kalshi's taker fee.

## Calendar

| Date | What settles or moves |
| --- | --- |
| Nov 9, after close | Take-Two Q2 FY27 earnings. Kalshi "preorders reported" needs a numeric figure. |
| Nov 12 | Preload opens. Delay risk is close to zero from here. |
| Unannounced, before Nov 19 | Review embargo lifts. Metacritic markets reprice within minutes. Run `mc watch`. |
| Nov 19 | Launch and *GTA VI: The Album*. Radio-song and album-feature markets settle on the tracklist. |
| Nov 20–26 | Luminate tracking week for the album's streams, units and pure sales markets. |
| Nov 26, 10 AM ET | Both Metacritic markets settle on the default-platform Metascore. |
| Dec 5 chart | Billboard 200 #1 market. |
| Jan 31, 2027 | Kalshi's 24-hour sales record market. It resolves on the Guinness World Records title, not on Take-Two's own headline. |

## Caveats

- Liquidity is thin: most order books hold a few thousand dollars per side.
- International Polymarket is closed to US persons. Kalshi is US-regulated.
- Every rule summary here is a paraphrase. Read the venue's rules before trading.

## Next modules

- Album tracker: daily Spotify counts from kworb, scaled to Luminate US totals, against the Kalshi streams and units ladders.
- Tracklist watcher: Rockstar Newswire and the official music page, priced against every song and artist market.
- Press-release watcher: Take-Two IR, for the preorder and sales-record markets.
