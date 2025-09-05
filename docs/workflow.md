# API Workflow

## Overzicht

De Bedrijfsanalyse API biedt drie verschillende analyse-endpoints voor Nederlandse bedrijven. Elk endpoint heeft zijn eigen workflow en gebruik case.

## 1. Standard Analysis (`/analyze-company`)

### Workflow
1. **Input validatie**: Bedrijfsnaam (verplicht), KvK nummer (optioneel)
2. **KvK lookup**: Als KvK nummer beschikbaar → ophalen bedrijfsgegevens
3. **Legal cases**: Zoeken naar rechtszaken via rechtspraak.nl
4. **News analysis**: AI-gedreven nieuwsanalyse met OpenAI
5. **Risk assessment**: Gecombineerde risicoanalyse
6. **Response**: Volledige analyse met alle componenten

### Gebruik
- Algemene bedrijfsanalyse
- Due diligence onderzoek
- Risicobeoordeling

## 2. Nederlandse Analyse (`/nederlands-bedrijf-analyse`)

### Workflow
1. **Input validatie**: Bedrijfsnaam + contactpersoon (beide verplicht)
2. **Legal check**: VERPLICHTE rechtspraak.nl check
3. **Dutch news priority**: Focus op Nederlandse nieuwsbronnen (FD, NRC, NOS)
4. **Structured output**: Nederlandse rapportage format
5. **Response**: Gestructureerde analyse in het Nederlands

### Gebruik
- Nederlandse bedrijven specifiek
- Contactpersoon betrokken onderzoek
- Nederlandse compliance

## 3. Simple Analysis (`/analyze-company-simple`)

### Workflow
1. **Input validatie**: Alleen bedrijfsnaam
2. **Parallel processing**: Gelijktijdig web + legal search
3. **Simple JSON output**: Basis informatie zonder diepgaande analyse
4. **Response**: Vereenvoudigde JSON structuur

### Gebruik
- Snelle basis checks
- Eenvoudige integraties
- Beperkte informatie behoefte

## Technische Details

### Response Times
- Standard analysis: < 30 seconden
- Deep search: < 60 seconden maximaal
- Simple analysis: < 15 seconden

### Rate Limiting
- 100 requests/uur per API key
- 1 request/seconde naar rechtspraak.nl
- 500 requests/dag KvK API limiet

### Error Handling
- HTTP 200: Succesvolle analyse
- HTTP 400: Validatie fouten
- HTTP 404: KvK nummer niet gevonden
- HTTP 429: Rate limit bereikt
- HTTP 500: Server fouten

## Integraties

### Externe APIs
1. **KvK API**: Optioneel, 500/dag limiet
2. **Rechtspraak.nl**: Verplicht, 1/sec limiet
3. **OpenAI GPT-4**: AI analyse, 30s timeout

### Veiligheid
- API key authenticatie (X-API-Key header)
- Geen persistente data opslag (GDPR)
- HTTPS verplicht
- Input validatie via Pydantic