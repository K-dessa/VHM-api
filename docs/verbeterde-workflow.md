API Workflow (Verbeterde versie zonder KvK, met aangepaste news-workflow)

1) Standard Analysis (/analyze-company)

Workflow
	1.	Input validatie
	•	Bedrijfsnaam (verplicht)
	3.	Web crawling (Crawl4AI)
	•	Seed: officiële website + relevante subpagina’s
	•	Config: markdown=True, remove_boilerplate=True, same_domain=True, max_depth=2, obey_robots_txt=True
	4.	News collection (intern, vernieuwd)
	•	Google News RSS feed ophalen:
https://news.google.com/rss/search?q="<BEDRIJFSNAAM>"&hl=nl&gl=NL&ceid=NL:nl
	•	RSS-items filteren: verwijder paywall-bronnen (NRC, FD, Volkskrant, Telegraaf)
	•	Overgebleven links optioneel crawlen met Crawl4AI (indien vrij toegankelijk)
	•	Google Custom Search JSON API voor aanvullende webresultaten (NL voorkeur)
	5.	News analysis (AI)
	•	Gebruik RSS-metadata + crawled content van open artikelen
	6.	Risk assessment
	•	AI combineert nieuws en crawl-data
	7.	Response
	•	Ongewijzigd (volledige analyse JSON)

⸻

2) Nederlandse Analyse (/nederlands-bedrijf-analyse)

Workflow
	1.	Input validatie
	•	Bedrijfsnaam (verplicht)
	•	Contactpersoon (verplicht)
	3.	Crawl4AI web crawling (NL focus)
	•	Alleen .nl domeinen en officiële pers/rapportpagina’s
	4.	Dutch news collection (intern, vernieuwd)
	•	Google News RSS feed NL (hl=nl&gl=NL)
	•	Whitelist NL-bronnen (NOS, NU.nl, RTL Z, BNR, regionale omroepen)
	•	Eventueel zoekfeed met contactpersoon toevoegen
	•	Google Custom Search JSON API met 'site:.nl' voor aanvullende links (handig voor kleinere bedrijven)
	•	Crawl alleen de open links
	5.	Dutch news analysis (AI)
	•	Combineer RSS + open crawls
	6.	Response
	•	Ongewijzigd (NL rapport JSON)

⸻

3) Simple Analysis (/analyze-company-simple)

Workflow
	1.	Input validatie
	•	Alleen bedrijfsnaam
	2.	Parallel processing
	•	Google News RSS (max. 10 items, snelle fetch)
	•	Google Custom Search JSON API (kleine set, NL voorkeur)
	•	Crawl4AI maximaal 2–3 pagina’s (depth=1)
	3.	Simple AI analysis
	•	Korte samenvatting + highlights
	4.	Response
	•	Ongewijzigd (basis JSON)
