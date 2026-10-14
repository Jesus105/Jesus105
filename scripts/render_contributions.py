"""Render the public GitHub contribution calendar without API keys or dependencies."""

import argparse
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
import urllib.request


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.days = {}
        self.counts = {}
        self.tooltip = None
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'td' and attrs.get('data-date'):
            self.days[attrs['id']] = {
                'date': date.fromisoformat(attrs['data-date']),
                'level': int(attrs['data-level']),
            }
        if tag == 'tool-tip' and attrs.get('for'):
            self.tooltip = attrs['for']
            self.text = []

    def handle_data(self, text):
        if self.tooltip:
            self.text.append(text)

    def handle_endtag(self, tag):
        if tag != 'tool-tip' or not self.tooltip:
            return
        text = ''.join(self.text).strip()
        match = re.search(r'([\d,]+)\s+contribution', text)
        if match:
            self.counts[self.tooltip] = int(match.group(1).replace(',', ''))
        elif text.startswith('No contributions'):
            self.counts[self.tooltip] = 0
        self.tooltip = None


def load_calendar(username):
    request = urllib.request.Request(
        f'https://github.com/users/{username}/contributions',
        headers={'User-Agent': 'github-profile-calendar', 'Accept-Language': 'en-US,en;q=0.9'},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        source = response.read().decode()
    parser = CalendarParser()
    parser.feed(source)
    today = datetime.now(timezone.utc).date()
    days = []
    for identifier, day in parser.days.items():
        if day['date'] > today:
            continue
        if identifier not in parser.counts:
            raise ValueError(f'Missing contribution count for {day["date"]}; keeping existing images.')
        if not 0 <= day['level'] <= 4:
            raise ValueError('Unknown GitHub calendar intensity level.')
        days.append({**day, 'count': parser.counts[identifier]})
    days.sort(key=lambda day: day['date'])
    if not 350 <= len(days) <= 380:
        raise ValueError(f'Expected a full year of calendar data, received {len(days)} days.')
    if len({day['date'] for day in days}) != len(days):
        raise ValueError('Duplicate dates in the GitHub calendar.')
    if days[-1]['date'] < today - timedelta(days=2):
        raise ValueError('GitHub returned a stale calendar.')
    return days, today


def render(username, days, updated, dark=False):
    if dark:
        bg, ink, muted, border = '#201B2C', '#F3ECFF', '#BDB0D1', '#4A3B60'
        palette = ['#32283F', '#57406F', '#7D57A5', '#AB82D2', '#D2B0FB']
    else:
        bg, ink, muted, border = '#F8F4FF', '#35294B', '#726184', '#E4D8F2'
        palette = ['#EBE3F3', '#D6C1EC', '#B698D7', '#946DC2', '#6A4398']
    total = sum(day['count'] for day in days)
    start = days[0]['date'] - timedelta(days=(days[0]['date'].weekday() + 1) % 7)
    end = days[-1]['date']
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="280" viewBox="0 0 960 280" role="img" aria-labelledby="title desc">
<title id="title">{escape(username)}: {total:,} contributions in the past year</title>
<desc id="desc">Daily contribution counts from the public GitHub profile, {start.isoformat()} through {end.isoformat()}. Updated {updated.isoformat()}.</desc>
<rect x="1" y="1" width="958" height="278" rx="20" fill="{bg}" stroke="{border}"/>
<g font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif">
<text x="32" y="43" fill="{ink}" font-size="22" font-weight="650">A year in code</text>
<text x="928" y="43" text-anchor="end" fill="{ink}" font-size="19" font-weight="650">{total:,} contributions</text>
<text x="32" y="67" fill="{muted}" font-size="13">@{escape(username)} · {start.strftime('%b %Y')} — {end.strftime('%b %Y')}</text>''']
    step, size, left, top = 16, 12, 57, 108
    previous_label = -100
    for day in days:
        column = (day['date'] - start).days // 7
        row = (day['date'].weekday() + 1) % 7
        x, y = left + column * step, top + row * step
        if (day['date'].day == 1 or day == days[0]) and x - previous_label > 24 and x < 880:
            parts.append(f'<text x="{x}" y="96" fill="{muted}" font-size="11">{day["date"].strftime("%b")}</text>')
            previous_label = x
        count = day['count']
        label = f'{day["date"].isoformat()}: {count} contribution' + ('' if count == 1 else 's')
        parts.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="3" fill="{palette[day["level"]]}"><title>{label}</title></rect>')
    for label, row in [('Mon', 1), ('Wed', 3), ('Fri', 5)]:
        parts.append(f'<text x="20" y="{top + row * step + 10}" fill="{muted}" font-size="10">{label}</text>')
    parts.append(f'<text x="32" y="251" fill="{muted}" font-size="11">Updated {updated.strftime("%d %b %Y")} · GitHub contribution activity</text>')
    parts.append(f'<text x="767" y="251" fill="{muted}" font-size="11">Less</text>')
    for index, color in enumerate(palette):
        parts.append(f'<rect x="{801 + index * 17}" y="240" width="12" height="12" rx="3" fill="{color}"/>')
    parts.append(f'<text x="898" y="251" fill="{muted}" font-size="11">More</text></g></svg>')
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', default='Jesus105')
    parser.add_argument('--output-dir', type=Path, default=Path('assets'))
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', args.username):
        parser.error('Invalid GitHub username.')
    days, updated = load_calendar(args.username)
    # Fetch and validate everything before changing an existing image.
    images = {f'contributions-{theme}.svg': render(args.username, days, updated, theme == 'dark') for theme in ['light', 'dark']}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in images.items():
        destination = args.output_dir / name
        temporary = destination.with_suffix('.svg.tmp')
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(destination)
    print(f'Rendered {len(days)} days and {sum(day["count"] for day in days):,} real GitHub contributions.')


if __name__ == '__main__':
    main()
