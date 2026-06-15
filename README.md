# AI Investment Monitor

Beginner-friendly weekly monitor for AI infrastructure investment.

The program generates a Chinese Markdown report and saves both the report and a JSON data snapshot in the `reports` folder.

## What It Tracks

- Microsoft quarterly CapEx
- Meta quarterly CapEx
- Alphabet / Google quarterly CapEx
- Amazon AWS CapEx proxy
- NVIDIA Data Center Revenue from NVIDIA earnings releases

## What The Report Explains

The Chinese weekly report explains the impact on:

- Optical Chips
- Optical Modules
- CPO
- Advanced Packaging
- PCB

## New Upgrade Features

- Uses quarterly CapEx instead of annual CapEx.
- Adds Amazon AWS CapEx as an AWS / AI infrastructure proxy.
- Automatically parses NVIDIA Data Center Revenue from NVIDIA earnings releases when available.
- Creates an AI Infrastructure Score from 0 to 100.
- Shows last report score, current score, and score change.
- Adds an AI Infrastructure Traffic Light: Green / Bullish, Yellow / Neutral, Red / Risk.
- Compares each metric with the previous `reports/metrics_*.json` snapshot.
- Generates Bullish / Neutral / Bearish ratings for Optical Chip, Optical Module, CPO, Advanced Packaging, and PCB.
- Adds a final Chinese investment dashboard summary.
- Keeps Chinese report output.

## Project Structure

```text
.
+-- main.py
+-- requirements.txt
+-- README.md
+-- reports/
+-- .github/
    +-- workflows/
        +-- weekly-report.yml
```

## Local Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Generate the weekly report:

```bash
python main.py
```

Print the report in the terminal too:

```bash
python main.py --print
```

The output files are saved automatically:

```text
reports/ai_investment_monitor_YYYY-MM-DD.md
reports/metrics_YYYY-MM-DD.json
```

## AI Infrastructure Score

The score is a simple 0-100 indicator:

- 80-100: very strong AI infrastructure cycle
- 60-79: strong, but watch marginal changes
- 40-59: neutral
- 0-39: weak or slowing

The score combines:

- Total quarterly CapEx from Microsoft, Meta, Alphabet, and Amazon
- NVIDIA Data Center Revenue
- Trend momentum compared with the previous report

## Traffic Light

The report includes:

- Green = Bullish
- Yellow = Neutral
- Red = Risk

It also shows:

- Last report score
- Current score
- Score change

## Industry Ratings

The report creates Chinese dashboard ratings for:

- Optical Chip
- Optical Module
- CPO
- Advanced Packaging
- PCB

Rating meanings:

- Bullish: strong score and supportive trend momentum.
- Neutral: demand is supported, but confirmation is mixed.
- Bearish: score or trend momentum is weak.

These are research signals only, not investment advice.

## Data Notes

- CapEx comes from the SEC companyfacts API.
- The script chooses the latest fiscal period end date first, not just the latest filing date. This prevents old comparative periods, such as Amazon FY2017 data re-filed in a newer report, from being treated as the latest quarter.
- Q2 and Q3 cash-flow CapEx are usually year-to-date values, so the script estimates single-quarter CapEx by subtracting the prior YTD quarter.
- Q4 is estimated as full-year CapEx minus Q3 YTD CapEx.
- Amazon does not consistently disclose AWS-only CapEx, so Amazon total CapEx is used as a proxy.
- NVIDIA segment revenue is parsed from NVIDIA earnings release pages. If the page is unavailable or the format changes, the script uses a fallback value and notes that in the report.

## GitHub Actions

`.github/workflows/weekly-report.yml` runs every Monday and can also be started manually from GitHub Actions. It installs dependencies, runs `python main.py`, and commits new files under `reports/`.

## Disclaimer

This project is for learning and research support only. It is not investment advice.
