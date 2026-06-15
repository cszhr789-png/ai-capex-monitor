from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests


REPORTS_DIR = Path("reports")


def u(text: str) -> str:
    """Decode escaped Chinese text while keeping this source file ASCII-safe."""
    return text.encode("ascii").decode("unicode_escape")


SIGNAL_BUY = u("\\u4e70\\u5165")
SIGNAL_HOLD = u("\\u6301\\u6709")
SIGNAL_CAUTION = u("\\u8c28\\u614e")
RATING_BULLISH = "Bullish"
RATING_NEUTRAL = "Neutral"
RATING_BEARISH = "Bearish"


@dataclass
class Metric:
    company: str
    metric_name: str
    fiscal_period: str
    value_usd_billions: float
    source: str
    note: str


COMPANIES = {
    "Microsoft": {
        "cik": "0000789019",
        "metric_name": "Quarterly CapEx",
        "tag": "PaymentsToAcquirePropertyPlantAndEquipment",
    },
    "Meta": {
        "cik": "0001326801",
        "metric_name": "Quarterly CapEx",
        "tag": "PaymentsToAcquirePropertyPlantAndEquipment",
    },
    "Alphabet (Google)": {
        "cik": "0001652044",
        "metric_name": "Quarterly CapEx",
        "tag": "PaymentsToAcquirePropertyPlantAndEquipment",
    },
    "Amazon AWS CapEx": {
        "cik": "0001018724",
        "metric_name": "AWS CapEx Proxy",
        "tag": "PaymentsToAcquirePropertyPlantAndEquipment",
    },
}


CAPEX_FALLBACKS = {
    "Microsoft": Metric("Microsoft", "Quarterly CapEx", "Manual baseline", 14.9, "Manual fallback", u("\\u8bf7\\u7528\\u6700\\u65b0 10-Q/10-K \\u73b0\\u91d1\\u6d41\\u91cf\\u8868\\u66f4\\u65b0\\u3002")),
    "Meta": Metric("Meta", "Quarterly CapEx", "Manual baseline", 13.7, "Manual fallback", u("\\u8bf7\\u7528\\u6700\\u65b0 10-Q/10-K \\u73b0\\u91d1\\u6d41\\u91cf\\u8868\\u66f4\\u65b0\\u3002")),
    "Alphabet (Google)": Metric("Alphabet (Google)", "Quarterly CapEx", "Manual baseline", 17.2, "Manual fallback", u("\\u8bf7\\u7528\\u6700\\u65b0 10-Q/10-K \\u73b0\\u91d1\\u6d41\\u91cf\\u8868\\u66f4\\u65b0\\u3002")),
    "Amazon AWS CapEx": Metric("Amazon AWS CapEx", "AWS CapEx Proxy", "Manual baseline", 26.3, "Manual fallback", u("Amazon \\u4e0d\\u5355\\u72ec\\u62ab\\u9732 AWS CapEx\\uff0c\\u672c\\u9879\\u4f7f\\u7528 Amazon \\u6574\\u4f53 CapEx \\u4f5c\\u4e3a AWS/AI \\u57fa\\u7840\\u8bbe\\u65bd\\u4ee3\\u7406\\u6307\\u6807\\u3002")),
}


NVIDIA_EARNINGS_URLS = [
    "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-fourth-quarter-and-fiscal-2026",
    "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-2026",
    "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-2026",
    "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-first-quarter-fiscal-2026",
]


NVIDIA_FALLBACK = Metric(
    company="NVIDIA",
    metric_name="Data Center Revenue",
    fiscal_period="Manual baseline",
    value_usd_billions=62.3,
    source="Manual fallback",
    note=u("\\u82e5\\u65e0\\u6cd5\\u8bbf\\u95ee NVIDIA earnings release\\uff0c\\u4f7f\\u7528\\u5185\\u7f6e\\u5907\\u7528\\u503c\\u3002\\u8bf7\\u5728\\u6700\\u65b0\\u8d22\\u62a5\\u53d1\\u5e03\\u540e\\u6838\\u5bf9\\u3002"),
)


def sec_headers() -> dict[str, str]:
    return {
        "User-Agent": "ai-investment-monitor beginner-project contact@example.com",
        "Accept-Encoding": "gzip, deflate",
    }


def fetch_json(url: str) -> dict[str, Any]:
    response = requests.get(url, headers=sec_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_text(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": sec_headers()["User-Agent"]}, timeout=30)
    response.raise_for_status()
    return response.text


def fetch_companyfacts(cik: str) -> dict[str, Any]:
    return fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")


def usd_facts(companyfacts: dict[str, Any], tag: str) -> list[dict[str, Any]]:
    return companyfacts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", [])


def latest_quarterly_capex_fact(companyfacts: dict[str, Any], tag: str) -> tuple[str, float] | None:
    facts = [
        fact
        for fact in usd_facts(companyfacts, tag)
        if fact.get("form") in {"10-Q", "10-K"}
        and fact.get("fy")
        and fact.get("fp") in {"Q1", "Q2", "Q3", "FY"}
        and fact.get("val") is not None
        and fact.get("filed")
        and fact.get("end")
    ]
    if not facts:
        return None

    # SEC companyfacts can include old comparative periods in newer filings.
    # Use the latest fiscal period end date first, then filing date.
    latest = max(facts, key=lambda item: (item.get("end", ""), item.get("filed", ""), item.get("fy", 0), item.get("fp", "")))
    fy = latest["fy"]
    fp = latest["fp"]
    value = abs(float(latest["val"]))

    if fp == "Q1":
        return f"FY{fy} Q1 filed {latest['filed']}", value / 1_000_000_000

    same_year = [fact for fact in facts if fact.get("fy") == fy]
    if fp in {"Q2", "Q3"}:
        previous_fp = "Q1" if fp == "Q2" else "Q2"
        previous_candidates = [fact for fact in same_year if fact.get("fp") == previous_fp]
        if previous_candidates:
            previous = max(previous_candidates, key=lambda item: (item.get("end", ""), item.get("filed", "")))
            return f"FY{fy} {fp} filed {latest['filed']}", abs(value - abs(float(previous["val"]))) / 1_000_000_000

    if fp == "FY":
        q3_candidates = [fact for fact in same_year if fact.get("fp") == "Q3"]
        if q3_candidates:
            q3 = max(q3_candidates, key=lambda item: (item.get("end", ""), item.get("filed", "")))
            return f"FY{fy} Q4 estimated from FY-Q3 filed {latest['filed']}", abs(value - abs(float(q3["val"]))) / 1_000_000_000

    return f"FY{fy} {fp} filed {latest['filed']} YTD fallback", value / 1_000_000_000


def fetch_capex_metric(company: str, config: dict[str, str]) -> Metric:
    try:
        result = latest_quarterly_capex_fact(fetch_companyfacts(config["cik"]), config["tag"])
        if not result:
            raise ValueError("No quarterly USD CapEx fact found.")
        fiscal_period, value = result
        note = u("SEC companyfacts \\u81ea\\u52a8\\u6293\\u53d6\\uff1bQ2/Q3 \\u4f7f\\u7528 YTD \\u5dee\\u989d\\u4f30\\u7b97\\u5355\\u5b63\\uff0cQ4 \\u4f7f\\u7528 FY-Q3 \\u4f30\\u7b97\\u3002")
        if company == "Amazon AWS CapEx":
            note += u(" Amazon \\u4e0d\\u5355\\u72ec\\u62ab\\u9732 AWS CapEx\\uff0c\\u56e0\\u6b64\\u7528 Amazon \\u6574\\u4f53 CapEx \\u4f5c\\u4e3a AWS/AI \\u57fa\\u7840\\u8bbe\\u65bd\\u4ee3\\u7406\\u6307\\u6807\\u3002")
        return Metric(company, config["metric_name"], fiscal_period, value, f"SEC companyfacts CIK {config['cik']}, tag {config['tag']}", note)
    except Exception as exc:
        fallback = CAPEX_FALLBACKS[company]
        failed = u("\\u6293\\u53d6\\u5931\\u8d25")
        return Metric(fallback.company, fallback.metric_name, fallback.fiscal_period, fallback.value_usd_billions, fallback.source, f"{fallback.note} {failed}:{exc}")


def discover_nvidia_earnings_urls() -> list[str]:
    urls = list(NVIDIA_EARNINGS_URLS)
    try:
        html = fetch_text("https://nvidianews.nvidia.com/news")
        absolute_urls = re.findall(r"https://nvidianews\.nvidia\.com/news/nvidia-announces-financial-results-for-[^\"'<\s]+", html)
        relative_urls = re.findall(r"href=[\"'](/news/nvidia-announces-financial-results-for-[^\"']+)[\"']", html)
        discovered = absolute_urls + [f"https://nvidianews.nvidia.com{url}" for url in relative_urls]
        for url in discovered:
            if url not in urls:
                urls.insert(0, url)
    except Exception:
        pass
    return urls


def parse_nvidia_data_center_revenue(text: str) -> float | None:
    clean = re.sub(r"\s+", " ", text)
    patterns = [
        r"Data Center revenue(?: was| of)?(?: a record)? \$([0-9]+(?:\.[0-9]+)?) billion",
        r"Data Center.*?quarter revenue was(?: a record)? \$([0-9]+(?:\.[0-9]+)?) billion",
        r"Record quarterly Data Center revenue of \$([0-9]+(?:\.[0-9]+)?) billion",
    ]
    for pattern in patterns:
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def parse_nvidia_period(text: str) -> str:
    title = re.search(r"NVIDIA Announces Financial Results for ([^<\n]+)", text, flags=re.IGNORECASE)
    date_match = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}", text)
    return f"{title.group(1).strip() if title else 'latest earnings release'}, {date_match.group(0) if date_match else 'date unavailable'}"


def fetch_nvidia_data_center_revenue() -> Metric:
    errors: list[str] = []
    for url in discover_nvidia_earnings_urls():
        try:
            text = fetch_text(url)
            value = parse_nvidia_data_center_revenue(text)
            if value is None:
                errors.append(f"{url}: no Data Center revenue match")
                continue
            return Metric("NVIDIA", "Data Center Revenue", parse_nvidia_period(text), value, url, u("\\u4ece NVIDIA earnings release \\u81ea\\u52a8\\u89e3\\u6790 Data Center revenue\\u3002"))
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    error_label = u("\\u6293\\u53d6\\u9519\\u8bef")
    return Metric(NVIDIA_FALLBACK.company, NVIDIA_FALLBACK.metric_name, NVIDIA_FALLBACK.fiscal_period, NVIDIA_FALLBACK.value_usd_billions, NVIDIA_FALLBACK.source, f"{NVIDIA_FALLBACK.note} {error_label}:{' | '.join(errors[:3])}")


def collect_metrics() -> list[Metric]:
    metrics = [fetch_capex_metric(company, config) for company, config in COMPANIES.items()]
    metrics.append(fetch_nvidia_data_center_revenue())
    return metrics


def metric_key(metric: Metric) -> str:
    return f"{metric.company}|{metric.metric_name}"


def normalize_snapshot_payload(payload: Any) -> tuple[list[dict[str, Any]], int | None, str | None]:
    if isinstance(payload, list):
        return payload, None, None
    if isinstance(payload, dict):
        metrics = payload.get("metrics", [])
        score = payload.get("ai_infrastructure_score")
        traffic_light = payload.get("traffic_light")
        return metrics if isinstance(metrics, list) else [], score, traffic_light
    return [], None, None


def load_previous_snapshot(today: date) -> tuple[Path | None, list[dict[str, Any]], int | None, str | None]:
    snapshot = find_previous_snapshot(today)
    if snapshot:
        try:
            metrics, score, traffic_light = normalize_snapshot_payload(json.loads(snapshot.read_text(encoding="utf-8")))
            return snapshot, metrics, score, traffic_light
        except Exception:
            return snapshot, [], None, None
    return None, [], None, None


def load_previous_metrics(today: date) -> list[dict[str, Any]]:
    snapshot = find_previous_snapshot(today)
    if snapshot:
        try:
            metrics, _, _ = normalize_snapshot_payload(json.loads(snapshot.read_text(encoding="utf-8")))
            return metrics
        except Exception:
            return []
    return []


def find_previous_snapshot(today: date) -> Path | None:
    if not REPORTS_DIR.exists():
        return None
    for snapshot in sorted(REPORTS_DIR.glob("metrics_*.json"), reverse=True):
        if snapshot.name != f"metrics_{today.isoformat()}.json":
            return snapshot
    return None


def trend_map(metrics: list[Metric], previous_metrics: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    previous_by_key = {f"{item.get('company')}|{item.get('metric_name')}": item for item in previous_metrics}
    trends: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        previous = previous_by_key.get(metric_key(metric))
        if not previous:
            trends[metric_key(metric)] = {"label": u("\\u65e0\\u53ef\\u6bd4\\u5386\\u53f2"), "delta": None, "delta_pct": None}
            continue
        previous_value = float(previous.get("value_usd_billions", 0) or 0)
        delta = metric.value_usd_billions - previous_value
        delta_pct = (delta / previous_value * 100) if previous_value else None
        label = u("\\u4e0a\\u5347") if delta > 0.2 else u("\\u4e0b\\u964d") if delta < -0.2 else u("\\u57fa\\u672c\\u6301\\u5e73")
        trends[metric_key(metric)] = {"label": label, "delta": delta, "delta_pct": delta_pct}
    return trends


def score_from_metric_dicts(metrics: list[dict[str, Any]]) -> int | None:
    if not metrics:
        return None
    total_capex = sum(
        float(item.get("value_usd_billions", 0) or 0)
        for item in metrics
        if item.get("metric_name") in {"Quarterly CapEx", "AWS CapEx Proxy"}
    )
    nvidia_dc = next(
        (
            float(item.get("value_usd_billions", 0) or 0)
            for item in metrics
            if item.get("company") == "NVIDIA" and item.get("metric_name") == "Data Center Revenue"
        ),
        0.0,
    )
    capex_score = min(total_capex / 80 * 55, 55)
    nvidia_score = min(nvidia_dc / 70 * 35, 35)
    return max(0, min(100, round(capex_score + nvidia_score + 5)))


def format_score_change(score_change: int | None) -> str:
    if score_change is None:
        return u("\\u65e0\\u53ef\\u6bd4\\u5386\\u53f2")
    return f"{score_change:+d}"


def format_trend(trend: dict[str, Any]) -> str:
    if trend["delta"] is None:
        return trend["label"]
    pct = "" if trend["delta_pct"] is None else f", {trend['delta_pct']:+.1f}%"
    unit = u("\\u5341\\u4ebf\\u7f8e\\u5143")
    return f"{trend['label']} {trend['delta']:+.1f} {unit}{pct}"


def calculate_ai_infrastructure_score(metrics: list[Metric], trends: dict[str, dict[str, Any]]) -> tuple[int, str]:
    total_capex = total_cloud_capex(metrics)
    nvidia_dc = next((item.value_usd_billions for item in metrics if item.company == "NVIDIA"), 0.0)
    capex_score = min(total_capex / 80 * 55, 55)
    nvidia_score = min(nvidia_dc / 70 * 35, 35)
    comparable = [trend for trend in trends.values() if trend["delta"] is not None]
    if comparable:
        positive = sum(1 for trend in comparable if trend["delta"] > 0.2)
        negative = sum(1 for trend in comparable if trend["delta"] < -0.2)
        momentum_score = max(0, min(10, 5 + positive * 1.5 - negative * 1.5))
    else:
        momentum_score = 5
    score = max(0, min(100, round(capex_score + nvidia_score + momentum_score)))
    if score >= 80:
        label = u("\\u5f88\\u5f3a\\uff1aAI \\u57fa\\u7840\\u8bbe\\u65bd\\u6295\\u8d44\\u5904\\u4e8e\\u9ad8\\u666f\\u6c14\\u533a\\u95f4")
    elif score >= 60:
        label = u("\\u504f\\u5f3a\\uff1a\\u9700\\u6c42\\u4ecd\\u6709\\u652f\\u6491\\uff0c\\u4f46\\u9700\\u8981\\u89c2\\u5bdf\\u8fb9\\u9645\\u53d8\\u5316")
    elif score >= 40:
        label = u("\\u4e2d\\u6027\\uff1a\\u6295\\u8d44\\u5f3a\\u5ea6\\u5c1a\\u53ef\\uff0c\\u8d8b\\u52bf\\u4fe1\\u53f7\\u4e0d\\u591f\\u4e00\\u81f4")
    else:
        label = u("\\u504f\\u5f31\\uff1a\\u5efa\\u8bae\\u91cd\\u70b9\\u89c2\\u5bdf\\u653e\\u7f13\\u98ce\\u9669")
    return score, label


def total_cloud_capex(metrics: list[Metric]) -> float:
    return sum(item.value_usd_billions for item in metrics if item.metric_name in {"Quarterly CapEx", "AWS CapEx Proxy"})


def average_capex_trend(metrics: list[Metric], trends: dict[str, dict[str, Any]]) -> float:
    deltas = [
        trends[metric_key(item)]["delta"]
        for item in metrics
        if item.metric_name in {"Quarterly CapEx", "AWS CapEx Proxy"} and trends[metric_key(item)]["delta"] is not None
    ]
    return sum(deltas) / len(deltas) if deltas else 0.0


def nvidia_trend_delta(metrics: list[Metric], trends: dict[str, dict[str, Any]]) -> float:
    nvidia = next((item for item in metrics if item.company == "NVIDIA"), None)
    if not nvidia:
        return 0.0
    delta = trends[metric_key(nvidia)]["delta"]
    return float(delta or 0.0)


def signal_for(score: int, capex_delta: float, nvidia_delta: float, buy_score: int, caution_score: int) -> str:
    if score >= buy_score and capex_delta >= -0.5 and nvidia_delta >= -1.0:
        return SIGNAL_BUY
    if score < caution_score or capex_delta < -2.0 or nvidia_delta < -3.0:
        return SIGNAL_CAUTION
    return SIGNAL_HOLD


def traffic_light(score: int, score_change: int | None) -> tuple[str, str]:
    if score >= 75 and (score_change is None or score_change >= -5):
        return "Green", "Bullish"
    if score >= 50 and (score_change is None or score_change >= -12):
        return "Yellow", "Neutral"
    return "Red", "Risk"


def industry_rating_for(score: int, capex_delta: float, nvidia_delta: float, bullish_score: int, bearish_score: int) -> str:
    if score >= bullish_score and capex_delta >= -0.5 and nvidia_delta >= -1.0:
        return RATING_BULLISH
    if score < bearish_score or capex_delta < -2.0 or nvidia_delta < -3.0:
        return RATING_BEARISH
    return RATING_NEUTRAL


def industry_ratings(metrics: list[Metric], trends: dict[str, dict[str, Any]], score: int) -> list[dict[str, str]]:
    capex_delta = average_capex_trend(metrics, trends)
    nvidia_delta = nvidia_trend_delta(metrics, trends)
    capex_phrase = u("\\u4e91\\u5382\\u5546 CapEx \\u52a8\\u91cf")
    nvidia_phrase = u("NVIDIA \\u6570\\u636e\\u4e2d\\u5fc3\\u52a8\\u91cf")

    return [
        {
            "sector": "Optical Chip",
            "rating": industry_rating_for(score, capex_delta, nvidia_delta, 75, 50),
            "reason": f"{capex_phrase} {capex_delta:+.1f}, {nvidia_phrase} {nvidia_delta:+.1f}; " + u("\\u9ad8\\u901f\\u5149\\u82af\\u7247\\u4e0e GPU \\u96c6\\u7fa4\\u6269\\u5bb9\\u76f8\\u5173\\u5ea6\\u9ad8\\u3002"),
        },
        {
            "sector": "Optical Module",
            "rating": industry_rating_for(score, capex_delta, nvidia_delta, 70, 48),
            "reason": f"{capex_phrase} {capex_delta:+.1f}, {nvidia_phrase} {nvidia_delta:+.1f}; 800G/1.6T " + u("\\u9700\\u6c42\\u4e0e\\u6570\\u636e\\u4e2d\\u5fc3\\u7f51\\u7edc\\u6295\\u5165\\u76f4\\u63a5\\u76f8\\u5173\\u3002"),
        },
        {
            "sector": "CPO",
            "rating": industry_rating_for(score, capex_delta, nvidia_delta, 82, 55),
            "reason": f"{capex_phrase} {capex_delta:+.1f}, {nvidia_phrase} {nvidia_delta:+.1f}; CPO " + u("\\u66f4\\u504f\\u4e2d\\u957f\\u671f\\u5bfc\\u5165\\uff0c\\u9700\\u8981\\u66f4\\u9ad8\\u7684\\u666f\\u6c14\\u5ea6\\u786e\\u8ba4\\u3002"),
        },
        {
            "sector": "Advanced Packaging",
            "rating": industry_rating_for(score, capex_delta, nvidia_delta, 72, 48),
            "reason": f"{capex_phrase} {capex_delta:+.1f}, {nvidia_phrase} {nvidia_delta:+.1f}; " + u("\\u5148\\u8fdb\\u5c01\\u88c5\\u4e0e GPU\\u3001HBM\\u3001CoWoS \\u9700\\u6c42\\u9ad8\\u5ea6\\u540c\\u6b65\\u3002"),
        },
        {
            "sector": "PCB",
            "rating": industry_rating_for(score, capex_delta, nvidia_delta, 68, 45),
            "reason": f"{capex_phrase} {capex_delta:+.1f}, {nvidia_phrase} {nvidia_delta:+.1f}; AI " + u("\\u670d\\u52a1\\u5668\\u548c\\u4ea4\\u6362\\u673a\\u6295\\u5165\\u63a8\\u52a8\\u9ad8\\u5c42\\u6570\\u3001\\u4f4e\\u635f\\u8017 PCB \\u9700\\u6c42\\u3002"),
        },
    ]


def industry_rating_rows(ratings: list[dict[str, str]]) -> str:
    return "\n".join(f"| {item['sector']} | {item['rating']} | {item['reason']} |" for item in ratings)


def rating_counts(ratings: list[dict[str, str]]) -> dict[str, int]:
    return {
        RATING_BULLISH: sum(1 for item in ratings if item["rating"] == RATING_BULLISH),
        RATING_NEUTRAL: sum(1 for item in ratings if item["rating"] == RATING_NEUTRAL),
        RATING_BEARISH: sum(1 for item in ratings if item["rating"] == RATING_BEARISH),
    }


def strength_label(value: float, metric_name: str) -> str:
    if metric_name == "Data Center Revenue":
        return u("\\u6781\\u5f3a") if value >= 50 else u("\\u5f3a") if value >= 35 else u("\\u4e2d\\u7b49\\u504f\\u5f3a") if value >= 20 else u("\\u89c2\\u5bdf")
    return u("\\u6781\\u5f3a") if value >= 20 else u("\\u5f3a") if value >= 12 else u("\\u4e2d\\u7b49\\u504f\\u5f3a") if value >= 6 else u("\\u89c2\\u5bdf")


def build_report(metrics: list[Metric], report_date: date | None = None) -> str:
    report_date = report_date or date.today()
    previous_snapshot, previous_metrics, stored_previous_score, _ = load_previous_snapshot(report_date)
    trends = trend_map(metrics, previous_metrics)
    score, score_label = calculate_ai_infrastructure_score(metrics, trends)
    previous_score = stored_previous_score if stored_previous_score is not None else score_from_metric_dicts(previous_metrics)
    score_change = score - previous_score if previous_score is not None else None
    light_color, light_signal = traffic_light(score, score_change)
    ratings = industry_ratings(metrics, trends, score)
    counts = rating_counts(ratings)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_capex = total_cloud_capex(metrics)
    nvidia_dc = next(item.value_usd_billions for item in metrics if item.company == "NVIDIA")
    comparison_base = previous_snapshot.name if previous_snapshot else u("\\u65e0\\u5386\\u53f2\\u62a5\\u544a\\uff0c\\u672c\\u671f\\u4f5c\\u4e3a\\u57fa\\u51c6")
    previous_score_text = str(previous_score) if previous_score is not None else u("\\u65e0\\u5386\\u53f2")
    rows = "\n".join(
        f"| {item.company} | {item.metric_name} | {item.fiscal_period} | {item.value_usd_billions:.1f} | {strength_label(item.value_usd_billions, item.metric_name)} | {format_trend(trends[metric_key(item)])} |"
        for item in metrics
    )
    ratings_table = industry_rating_rows(ratings)
    sources = "\n".join(f"- {item.company}: {item.source}. {item.note}" for item in metrics)

    template = u("""# AI \\u6295\\u8d44\\u76d1\\u63a7\\u5468\\u62a5

\\u751f\\u6210\\u65f6\\u95f4\\uff1a{generated_at}

## \\u4e00\\u3001\\u672c\\u5468\\u6838\\u5fc3\\u7ed3\\u8bba

AI Infrastructure Score\\uff1a**{score}/100**  
\\u8bc4\\u5206\\u89e3\\u8bfb\\uff1a{score_label}

AI Infrastructure Traffic Light\\uff1a**{light_color} / {light_signal}**

\\u672c\\u5468\\u56db\\u5bb6\\u4e91\\u5382\\u5546\\u5b63\\u5ea6 CapEx \\u5408\\u8ba1\\u7ea6 **{total_capex:.1f} \\u5341\\u4ebf\\u7f8e\\u5143**\\uff0cNVIDIA \\u6570\\u636e\\u4e2d\\u5fc3\\u6536\\u5165\\u7ea6 **{nvidia_dc:.1f} \\u5341\\u4ebf\\u7f8e\\u5143**\\u3002

\\u5bf9\\u6bd4\\u57fa\\u51c6\\uff1a**{comparison_base}**

| \\u9879\\u76ee | \\u6570\\u503c |
| --- | ---: |
| Last report score | {previous_score_text} |
| Current score | {score} |
| Score change | {score_change_text} |

## \\u4e8c\\u3001\\u6838\\u5fc3\\u6570\\u636e\\u4e0e\\u8d8b\\u52bf

| \\u516c\\u53f8 | \\u6307\\u6807 | \\u8d22\\u671f | \\u91d1\\u989d\\uff08\\u5341\\u4ebf\\u7f8e\\u5143\\uff09 | \\u5f3a\\u5ea6 | \\u8f83\\u4e0a\\u671f\\u8d8b\\u52bf |
| --- | --- | --- | ---: | --- | --- |
{rows}

## \\u4e09\\u3001\\u884c\\u4e1a\\u8bc4\\u7ea7

| \\u65b9\\u5411 | \\u8bc4\\u7ea7 | \\u539f\\u56e0 |
| --- | --- | --- |
{ratings_table}

## \\u56db\\u3001\\u8d8b\\u52bf\\u5206\\u6790

- \\u82e5\\u5b63\\u5ea6 CapEx \\u4e0e NVIDIA \\u6570\\u636e\\u4e2d\\u5fc3\\u6536\\u5165\\u540c\\u65f6\\u4e0a\\u5347\\uff0c\\u901a\\u5e38\\u610f\\u5473\\u7740 AI \\u670d\\u52a1\\u5668\\u3001GPU \\u96c6\\u7fa4\\u3001\\u6570\\u636e\\u4e2d\\u5fc3\\u7f51\\u7edc\\u548c\\u9ad8\\u901f\\u4e92\\u8fde\\u9700\\u6c42\\u589e\\u5f3a\\u3002
- \\u82e5 CapEx \\u4e0a\\u5347\\u4f46 NVIDIA \\u6536\\u5165\\u653e\\u7f13\\uff0c\\u9700\\u8981\\u89c2\\u5bdf GPU \\u4f9b\\u5e94\\u3001\\u8ba2\\u5355\\u8282\\u594f\\u6216\\u5e93\\u5b58\\u5438\\u6536\\u3002
- Amazon AWS CapEx \\u4f7f\\u7528 Amazon \\u6574\\u4f53 CapEx \\u4f5c\\u4e3a AWS/AI \\u57fa\\u7840\\u8bbe\\u65bd\\u4ee3\\u7406\\u6307\\u6807\\uff0c\\u56e0\\u4e3a\\u516c\\u53f8\\u4e0d\\u7a33\\u5b9a\\u62ab\\u9732 AWS \\u5355\\u72ec CapEx\\u3002

## \\u4e94\\u3001\\u4ea7\\u4e1a\\u94fe\\u5f71\\u54cd

### 1. \\u5149\\u82af\\u7247
\\u5b63\\u5ea6 CapEx \\u8d8a\\u9ad8\\uff0c\\u4ee3\\u8868\\u6570\\u636e\\u4e2d\\u5fc3\\u7f51\\u7edc\\u5347\\u7ea7\\u548c GPU \\u96c6\\u7fa4\\u6269\\u5bb9\\u8d8a\\u79ef\\u6781\\uff0c\\u9ad8\\u901f\\u5149\\u901a\\u4fe1\\u82af\\u7247\\u3001DSP\\u3001\\u6fc0\\u5149\\u5668\\u548c\\u7845\\u5149\\u65b9\\u6848\\u53d7\\u76ca\\u66f4\\u660e\\u663e\\u3002

### 2. \\u5149\\u6a21\\u5757
AI \\u96c6\\u7fa4\\u9700\\u8981\\u5927\\u91cf 800G \\u5149\\u6a21\\u5757\\uff0c\\u5e76\\u63a8\\u52a8 1.6T \\u5149\\u6a21\\u5757\\u9a8c\\u8bc1\\u548c\\u5bfc\\u5165\\u3002

### 3. CPO
CPO\\uff08\\u5171\\u5c01\\u88c5\\u5149\\u5b66\\uff09\\u662f\\u4e2d\\u957f\\u671f\\u6548\\u7387\\u5347\\u7ea7\\u65b9\\u5411\\uff0c\\u5728\\u5e26\\u5bbd\\u3001\\u529f\\u8017\\u548c\\u7aef\\u53e3\\u5bc6\\u5ea6\\u538b\\u529b\\u4e0a\\u5347\\u65f6\\u4ef7\\u503c\\u66f4\\u7a81\\u51fa\\u3002

### 4. \\u5148\\u8fdb\\u5c01\\u88c5
NVIDIA \\u6570\\u636e\\u4e2d\\u5fc3\\u6536\\u5165\\u662f GPU\\u3001HBM\\u3001CoWoS \\u548c\\u5148\\u8fdb\\u5c01\\u88c5\\u9700\\u6c42\\u7684\\u91cd\\u8981\\u540c\\u6b65\\u6307\\u6807\\u3002

### 5. PCB
AI \\u670d\\u52a1\\u5668\\u3001\\u4ea4\\u6362\\u673a\\u548c\\u9ad8\\u901f\\u4e92\\u8fde\\u63d0\\u5347 PCB \\u5c42\\u6570\\u3001\\u6750\\u6599\\u7b49\\u7ea7\\u548c\\u5236\\u9020\\u96be\\u5ea6\\uff0c\\u652f\\u6491\\u9ad8\\u901f PCB \\u548c\\u4f4e\\u635f\\u8017\\u6750\\u6599\\u9700\\u6c42\\u3002

## \\u516d\\u3001\\u6570\\u636e\\u6765\\u6e90\\u4e0e\\u5907\\u6ce8

{sources}

## \\u4e03\\u3001\\u6700\\u7ec8\\u6295\\u8d44\\u4eea\\u8868\\u76d8\\u6458\\u8981

- \\u603b\\u4f53\\u4fe1\\u53f7\\uff1a**{light_color} / {light_signal}**\\u3002
- \\u5206\\u6570\\u53d8\\u5316\\uff1a\\u4e0a\\u671f **{previous_score_text}**\\uff0c\\u672c\\u671f **{score}**\\uff0c\\u53d8\\u5316 **{score_change_text}**\\u3002
- \\u884c\\u4e1a\\u5206\\u5e03\\uff1aBullish **{bullish_count}** \\u4e2a\\uff0cNeutral **{neutral_count}** \\u4e2a\\uff0cBearish **{bearish_count}** \\u4e2a\\u3002
- \\u64cd\\u4f5c\\u542b\\u4e49\\uff1aGreen \\u4ee3\\u8868\\u504f\\u591a\\uff0cYellow \\u4ee3\\u8868\\u4e2d\\u6027\\u89c2\\u5bdf\\uff0cRed \\u4ee3\\u8868\\u98ce\\u9669\\u5347\\u9ad8\\u3002\\u672c\\u4eea\\u8868\\u76d8\\u4ec5\\u7528\\u4e8e\\u7814\\u7a76\\u8f85\\u52a9\\uff0c\\u4e0d\\u662f\\u4ea4\\u6613\\u6307\\u4ee4\\u3002

> \\u63d0\\u9192\\uff1a\\u672c\\u9879\\u76ee\\u7528\\u4e8e\\u5b66\\u4e60\\u548c\\u7814\\u7a76\\u8f85\\u52a9\\uff0c\\u4e0d\\u6784\\u6210\\u6295\\u8d44\\u5efa\\u8bae\\u3002
""")
    return template.format(
        generated_at=generated_at,
        score=score,
        score_label=score_label,
        light_color=light_color,
        light_signal=light_signal,
        total_capex=total_capex,
        nvidia_dc=nvidia_dc,
        comparison_base=comparison_base,
        previous_score_text=previous_score_text,
        score_change_text=format_score_change(score_change),
        rows=rows,
        ratings_table=ratings_table,
        sources=sources,
        bullish_count=counts[RATING_BULLISH],
        neutral_count=counts[RATING_NEUTRAL],
        bearish_count=counts[RATING_BEARISH],
    )


def save_report(content: str, report_date: date | None = None) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_date = report_date or date.today()
    output_path = REPORTS_DIR / f"ai_investment_monitor_{report_date.isoformat()}.md"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def save_json_snapshot(
    metrics: list[Metric],
    report_date: date | None = None,
    score: int | None = None,
    score_change: int | None = None,
    light_color: str | None = None,
    light_signal: str | None = None,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_date = report_date or date.today()
    output_path = REPORTS_DIR / f"metrics_{report_date.isoformat()}.json"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ai_infrastructure_score": score,
        "score_change": score_change,
        "traffic_light": light_color,
        "traffic_signal": light_signal,
        "metrics": [asdict(metric) for metric in metrics],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=u("\\u751f\\u6210\\u4e2d\\u6587 AI \\u6295\\u8d44\\u76d1\\u63a7\\u5468\\u62a5\\u3002"))
    parser.add_argument("--print", action="store_true", help=u("\\u5728\\u7ec8\\u7aef\\u6253\\u5370\\u62a5\\u544a\\u5185\\u5bb9\\u3002"))
    args = parser.parse_args()

    metrics = collect_metrics()
    _, previous_metrics, stored_previous_score, _ = load_previous_snapshot(date.today())
    trends = trend_map(metrics, previous_metrics)
    score, _ = calculate_ai_infrastructure_score(metrics, trends)
    previous_score = stored_previous_score if stored_previous_score is not None else score_from_metric_dicts(previous_metrics)
    score_change = score - previous_score if previous_score is not None else None
    light_color, light_signal = traffic_light(score, score_change)
    report = build_report(metrics)
    report_path = save_report(report)
    json_path = save_json_snapshot(metrics, score=score, score_change=score_change, light_color=light_color, light_signal=light_signal)

    if args.print:
        print(report)

    report_saved = u("\\u62a5\\u544a\\u5df2\\u4fdd\\u5b58")
    snapshot_saved = u("\\u6570\\u636e\\u5feb\\u7167\\u5df2\\u4fdd\\u5b58")
    print(f"{report_saved}:{report_path}")
    print(f"{snapshot_saved}:{json_path}")


if __name__ == "__main__":
    main()
