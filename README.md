# WebUntis MCP Server

Ein lokaler [MCP](https://modelcontextprotocol.io/)-Server (Model Context Protocol) fuer den Zugriff auf [WebUntis](https://www.untis.at/) Schuldaten. Ermoeglicht LLMs wie Claude den direkten Zugriff auf Stundenplan, Hausaufgaben, Klausuren, Fehlzeiten, Nachrichten und mehr.

> **Hinweis:** Dies ist ein inoffizielles Community-Projekt. Es besteht keine Verbindung zu Untis GmbH. Nutzung auf eigene Verantwortung.

## Features

| Tool | Beschreibung |
|------|-------------|
| `untis_daily_report` | **Eltern-Briefing**: Komplettueberblick -- Stundenplan morgen, Klausuren (7 Tage), Hausaufgaben (7 Tage), Fehlzeiten, Nachrichten |
| `untis_get_students` | Kinder/Schueler des Accounts auflisten (Eltern-Accounts) |
| `untis_get_timetable` | Stundenplan abrufen (mit aufgeloesten Fach-/Lehrer-/Raumnamen) |
| `untis_get_homework` | Aktuelle Hausaufgaben |
| `untis_get_exams` | Anstehende Klausuren und Tests |
| `untis_get_absences` | Fehlzeiten |
| `untis_get_messages` | Nachrichten (Posteingang) |
| `untis_get_school_info` | Schuljahr, Ferien, Stundenraster |
| `untis_raw_call` | Beliebiger JSON-RPC-Aufruf fuer nicht abgedeckte Endpunkte |

## Voraussetzungen

- Python 3.11+
- Ein Eltern- oder Schueler-Account bei [WebUntis](https://www.untis.at/)

## Installation

```bash
git clone <repo-url>
cd untis

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Konfiguration

### 1. Zugangsdaten hinterlegen

```bash
cp .env.example .env
```

Bearbeite `.env` mit deinen WebUntis-Zugangsdaten:

```
WEBUNTIS_SERVER=melpomene.webuntis.com
WEBUNTIS_SCHOOL=dhg-meersburg
WEBUNTIS_USER=dein-benutzername
WEBUNTIS_PASSWORD=dein-passwort
```

Den Servernamen und die Schulbezeichnung findest du in der URL deiner WebUntis-Instanz:
`https://<server>/WebUntis/?school=<school>#/...`

### 2. Claude Code einrichten

Fuege folgendes in deine Claude Code Projekt-Settings (`.claude/settings.json`) ein:

```json
{
  "mcpServers": {
    "untis-mcp": {
      "command": "/absoluter/pfad/zu/untis/start.sh",
      "args": []
    }
  }
}
```

## Nutzung

Starte Claude Code und frage einfach:

```
> Gib mir das Eltern-Briefing
> Welche Hausaufgaben gibt es?
> Zeig mir den Stundenplan fuer morgen
> Welche Klausuren stehen an?
> Gibt es neue Nachrichten?
```

### Standalone Daily Report

Das Eltern-Briefing kann auch ohne MCP direkt im Terminal ausgegeben werden:

```bash
./daily_report.sh
```

### Beispiel-Report

```markdown
# Eltern-Briefing (20.03.2026)

## Schueler (ID 1234)

### Auf einen Blick
- Stundenplan Mo: E, D, M, Chor
- **1 Klausur diese Woche**
- **2 Hausaufgaben** eingetragen

### Stundenplan Mo 23.03.2026
- **1. Stunde**: E, Raum A2.1
- **2. Stunde**: E, Raum A2.1
- **3. Stunde**: D, Raum A2.1
- **4. Stunde**: D, Raum A2.1
- **5. Stunde**: M, Raum A2.1
- **6. Stunde**: M, Raum A2.1
- **7. Stunde**: Chor, Raum MU1

### Klausuren & Tests (naechste 7 Tage)
- **25.03.2026**: Ge (KA)

### Hausaufgaben (naechste 7 Tage)
- **NWT**: Doku Projekt (bis 27.03.2026)
- **M**: S.122 Nr.6b) AB Nr.4 (bis 23.03.2026)

### Fehlzeiten
- Keine Fehlzeiten
```

## Technische Details

### Authentifizierung

Der Server nutzt zwei Protokolle der WebUntis-API:

1. **JSON-RPC 2.0** (`/WebUntis/jsonrpc.do`):
   - `authenticate` mit Benutzername/Passwort liefert `sessionId` (Cookie)
   - Stundenplan, Stammdaten, Vertretungen, Klausuren (RPC)
   - Session-Timeout ca. 10 min, automatische Re-Authentifizierung

2. **REST/WebAPI** (`/WebUntis/api/...`):
   - JWT-Token via `/api/token/new`
   - Hausaufgaben, Fehlzeiten, Nachrichten, Klausuren (REST)
   - Angereicherter Stundenplan via `/api/public/timetable/weekly/data`

### Eltern-Accounts

Bei Eltern-Accounts (personType=12) werden die Kinder automatisch ueber `/api/rest/view/v1/app/data` ermittelt. Der Stundenplan wird dann fuer das Kind (personType=5) abgerufen.

### API-Endpunkte

| Protokoll | Endpunkt | Beschreibung |
|-----------|----------|-------------|
| JSON-RPC | `getTimetable` | Stundenplan (nur IDs) |
| JSON-RPC | `getSubstitutions` | Vertretungen |
| JSON-RPC | `getHolidays` | Ferien |
| JSON-RPC | `getTimegridUnits` | Stundenraster |
| JSON-RPC | `getCurrentSchoolyear` | Schuljahr |
| REST | `/api/public/timetable/weekly/data` | Stundenplan mit Namen |
| REST | `/api/homeworks/lessons` | Hausaufgaben |
| REST | `/api/exams` | Klausuren |
| REST | `/api/classreg/absences/students` | Fehlzeiten |
| REST | `/api/rest/view/v1/messages` | Nachrichten |

## Lizenz

Dieses Projekt steht unter der [Unlicense](LICENSE) -- gemeinfrei, ohne jede Gewaehr.
