API Workflow (Verbeterde versie zonder KvK)

Overzicht

De Bedrijfsanalyse API biedt drie verschillende analyse-endpoints voor Nederlandse bedrijven.
Met Crawl4AI worden webpagina’s automatisch opgehaald, omgezet naar AI-klare Markdown en toegevoegd aan de analyse. Dit zorgt voor betere context en transparantie.

⸻

1. Standard Analysis (/analyze-company)

Workflow
	1.	Input validatie
	•	Bedrijfsnaam (verplicht)
	2.	Legal cases
	•	Rechtspraak.nl check (API, max. 1/sec)
	3.	Web crawling (Crawl4AI)
	•	Seed: officiële website + relevante subpagina’s
	•	Output: AI-klare Markdown (boilerplate verwijderd)
	•	Chunking per sectie
	4.	News analysis (AI)
	•	Nederlandse & internationale bronnen
	•	Crawled content + live nieuws in analyse
	5.	Risk assessment
	•	AI combineert legal, nieuws en crawl-data
	6.	Response
	•	Volledige analyse (JSON) met alle componenten

Gebruik
	•	Due diligence
	•	Risicobeoordeling
	•	Investor reports

⸻

2. Nederlandse Analyse (/nederlands-bedrijf-analyse)

Workflow
	1.	Input validatie
	•	Bedrijfsnaam (verplicht)
	•	Contactpersoon (verplicht)
	2.	Legal check (verplicht)
	•	Rechtspraak.nl API-check
	3.	Crawl4AI web crawling
	•	Focus op Nederlandse sites (.nl domeinen)
	•	Output in Nederlands Markdown
	4.	Dutch news priority
	•	FD, NRC, NOS, NU.nl etc. crawlen & analyseren
	5.	Structured output
	•	Rapportage in het Nederlands
	6.	Response
	•	JSON rapport, Nederlands format

Gebruik
	•	Compliance
	•	Lokale marktanalyses
	•	Nederlandse bedrijfsrapportages

⸻

3. Simple Analysis (/analyze-company-simple)

Workflow
	1.	Input validatie
	•	Alleen bedrijfsnaam
	2.	Parallel processing
	•	Crawl4AI (max. 2–3 pagina’s, depth 1)
	•	Rechtspraak.nl API
	3.	Simple AI analysis
	•	Snelle interpretatie van crawled content
	4.	Response
	•	Basis JSON met highlights

Gebruik
	•	Snelle checks
	•	Integratie in dashboards
	•	Lage latentie analyses

⸻

Technische Details

Crawl4AI Configuratie
	•	Markdown output: markdown=True
	•	Remove boilerplate: True
	•	Max depth: 2 (standaard), 1 bij Simple Analysis
	•	Same domain: True (geen domein hops)
	•	Robots respecteren: obey_robots_txt=True

Response Times
	•	Standard: < 30s
	•	Dutch: < 40s
	•	Simple: < 15s

Rate Limiting
	•	Rechtspraak.nl: 1 request/sec
	•	Crawl4AI: adaptive throttling

Error Handling
	•	200: Succesvolle analyse
	•	400: Validatiefout
	•	404: Bedrijf niet gevonden (bij crawl)
	•	429: Rate limit bereikt
	•	500: Server error

⸻

Integraties
	•	Rechtspraak.nl API – juridische zaken
	•	Crawl4AI – AI-klare webcontent
	•	OpenAI GPT-4 – analyse & synthese

⸻

Veiligheid & Privacy
	•	API key authenticatie via X-API-Key
	•	Geen persistente opslag van crawldata (alleen runtime)
	•	HTTPS verplicht
	•	GDPR-proof: tijdelijke verwerking, geen logging van persoonsgegevens

