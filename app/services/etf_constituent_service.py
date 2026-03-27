import json
import shutil
import subprocess
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen


class EtfConstituentServiceError(Exception):
    pass


@dataclass(slots=True)
class EtfConstituentSnapshot:
    etf_code: str
    codes: list[str]
    source_url: str
    announce_date: str | None
    trade_date: str | None


class EtfConstituentService:
    def get_0050_constituents(self) -> EtfConstituentSnapshot:
        return self.get_constituents("0050")

    def get_constituents(self, etf_code: str) -> EtfConstituentSnapshot:
        source_url = f"https://www.yuantaetfs.com/tradeInfo/pcf/{etf_code}"
        html = self._fetch_html(source_url)
        payload = self._extract_pcf_payload(html)

        fund_composition = payload.get("InKind", {}).get("FundComposition", [])
        codes = [row["stkcd"] for row in fund_composition if isinstance(row.get("stkcd"), str) and row["stkcd"].isdigit()]
        if not codes:
            raise EtfConstituentServiceError(f"Unable to parse constituent list from {source_url}.")

        pcf = payload.get("PCF", {})
        trade_date = pcf.get("trandate")
        if isinstance(trade_date, str) and len(trade_date) == 8:
            trade_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}"

        announce_date = pcf.get("anndate")
        if isinstance(announce_date, str) and len(announce_date) == 8:
            announce_date = f"{announce_date[:4]}-{announce_date[4:6]}-{announce_date[6:]}"

        return EtfConstituentSnapshot(
            etf_code=etf_code,
            codes=codes,
            source_url=source_url,
            announce_date=announce_date if isinstance(announce_date, str) else None,
            trade_date=trade_date if isinstance(trade_date, str) else None,
        )

    def _fetch_html(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="ignore")
        except URLError as exc:
            raise EtfConstituentServiceError(f"Unable to fetch ETF constituent data from {url}.") from exc

    def _extract_pcf_payload(self, html: str) -> dict:
        node = shutil.which("node")
        if node is None:
            raise EtfConstituentServiceError("Node.js is required to parse the official Yuanta PCF payload.")

        parser = """
const fs = require('fs');
const html = fs.readFileSync(0, 'utf8');
const match = html.match(/window\\.__NUXT__=\\(function[\\s\\S]*?<\\/script>/);
if (!match) {
  console.error('NUXT payload not found');
  process.exit(1);
}
const script = match[0].replace(/<\\/script>$/, '');
const window = {};
eval(script);
const payload = window.__NUXT__?.data?.[1]?.pcfData;
if (!payload) {
  console.error('PCF payload not found');
  process.exit(1);
}
process.stdout.write(JSON.stringify(payload));
"""

        try:
            result = subprocess.run(
                [node, "-e", parser],
                input=html,
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=True,
                timeout=20,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise EtfConstituentServiceError("Unable to parse the official Yuanta PCF payload.") from exc

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise EtfConstituentServiceError("Invalid ETF constituent payload returned by parser.") from exc
