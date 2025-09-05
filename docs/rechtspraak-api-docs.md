Rechtspraak Open Data — Kern API Endpoints

Compacte, praktische API-docs van de belangrijkste endpoints om uitspraken te vinden (ECLI-index), inhoud/metadata op te halen, images te laden en benodigde waardelijsten te gebruiken. Bron: Technische-documentatie Open Data van de Rechtspraak v1.15 (20-03-2019)

⸻

Basis
	•	Base URL: https://data.rechtspraak.nl/
	•	Formaten:
	•	Zoeken levert Atom XML met ECLI’s en samenvattingen.
	•	Content/metadata levert RDF/XML + (indien beschikbaar) de HTML/XML uitspraak.
	•	Images leveren binaire bestanden.
	•	Waardelijsten leveren XML.

Fair use: “Don’t hammer the server” — beperk gelijktijdige requests; gebruik filters/paging (max, from).

⸻

1) Zoeken in de ECLI-index

GET /uitspraken/zoeken
Geeft een Atom feed met ECLI’s die voldoen aan de query (metadata-index).

Belangrijkste query-parameters
	•	type — "Uitspraak" of "Conclusie". (0..1)
	•	creator — instantie-identifier (URI uit waardelijst). (0..n, OR)
	•	date — uitspraakdatum YYYY-MM-DD; 1× = exact die dag, 2× = vanaf datum1 t/m datum2. (0,1 of 2)
	•	subject — rechtsgebied (URI). (0..n, OR)
	•	modified — wijzigingsperiode YYYY-MM-DDThh:mm:ss; 1× = vanaf timestamp tot nu, 2× = bereik.
	•	return — "DOC" = alleen ECLI’s waarvoor ook document beschikbaar is. (0..1)
	•	replaces — oud LJN om bijbehorende ECLI(’s) te vinden. (0..n)
	•	max — max resultaten per pagina (default én max 1000).
	•	from — offset voor paging (startindex).
	•	sort — "ASC" (default op modified) of "DESC".

Voorbeelden
	•	Alle conclusies in mei 2011:

GET https://data.rechtspraak.nl/uitspraken/zoeken?type=conclusie&date=2011-05-01&date=2011-05-30


	•	Alle sinds 1 aug 2012 gewijzigde ECLI’s met document:

GET https://data.rechtspraak.nl/uitspraken/zoeken?modified=2012-08-01T00:00:00&return=DOC


	•	Paging (500 per pagina):

?modified=1995-01-01T12:00:00&max=500
?modified=1995-01-01T12:00:00&max=500&from=501



Response (Atom)
	•	feed/title, feed/subtitle (aantal), feed/updated, meerdere entry items met id (ECLI), link, updated, optioneel summary. Er kunnen ook entry deleted="doc" of deleted="ecli" items voorkomen.

⸻

2) Content & metadata per ECLI

GET /uitspraken/content
Haalt metadata en (indien beschikbaar) het document op voor één ECLI.

Query-parameters
	•	id — de ECLI (verplicht), bijv. ECLI:NL:HR:2014:952.
	•	return — "META" om alleen metadata te krijgen. (optioneel)

Voorbeelden
	•	Alleen metadata:

GET https://data.rechtspraak.nl/uitspraken/content?id=ECLI:NL:HR:2014:952&return=META


	•	Metadata + document (indien beschikbaar):

GET https://data.rechtspraak.nl/uitspraken/content?id=ECLI:NL:RVS:2014:1423



Response
	•	RDF/XML met ECLI-metadata (o.a. dcterms:identifier, dcterms:issued “Publicatiedatum”, dcterms:modified, dcterms:creator (instantie), dcterms:date (uitspraakdatum), psi:zaaknummer, dcterms:type (“Uitspraak”/“Conclusie”), psi:procedure, dcterms:subject (rechtsgebied), formele relaties (dcterms:relation), verwijzingen (dcterms:references), vindplaatsen (dcterms:hasVersion), etc.).
	•	Optioneel: inhoudsindicatie en de uitspraak/conclusie tekststructuur conform Rechtspraak schema.

⸻

3) Images binnen uitspraken

GET /uitspraken/image
Laadt losse image resources die in de uitspraak-XML via imagedata zijn gerefereerd.

Query-parameters
	•	id — image-identifier (GUID-achtig), te vinden in <imagedata linkend="image-identifier-2" />.

Voorbeeld

GET https://data.rechtspraak.nl/uitspraken/image?id=image-identifier-2


⸻

4) Waardelijsten (referentiedata)

Nodig voor o.a. creator (instanties), subject (rechtsgebieden) en psi:procedure. De waardelijsten staan als XML gepubliceerd en worden in de docs genoemd.

Voorbeelden van lijsten
	•	Instanties (NL-rechtsprekende instanties; bevat Identifier (URI), Naam, Afkorting, Type, BeginDate, optioneel EndDate).
	•	BuitenlandseInstanties (geen NL-ECLI; Identifier, Naam, optioneel Afkorting, Type).
	•	Rechtsgebieden (taxonomie met geneste rechtsgebieden; Identifier, Naam).
	•	ProcedureSoorten (procedure-typen; Identifier, Naam).
	•	FormeleRelaties (typen relaties + gevolg/aanleg labels).
	•	Overzicht bijzondere LJN’s/ECLI’s/vindplaatsen (o.a. LJN zonder ECLI, NL:XX). Beschikbaar via: https://data.rechtspraak.nl/Waardelijst/NietNederlandseUitspraken (XML).

Gebruik de Identifier-URI’s uit deze lijsten in je zoek-queries (creator, subject) en bij interpretatie van psi:procedure en formele relaties.

⸻

Fouten, zero-results & encoding
	•	Geen resultaten: aantal staat in feed/subtitle; geen entry elementen.
	•	HTTP-fouten: standaard HTTP 1.1 codes; inhoudelijke fouten bij ongeldige parameters → 400 Bad Request + uitleg.
	•	URL-encoding: percent-encoding (bijv. %20 voor spatie). Reserve characters: ?, &, =.

⸻

Quick cURL snippets

Zoek (laatste wijzigingen, met document, aflopend):

curl -s "https://data.rechtspraak.nl/uitspraken/zoeken?modified=2024-01-01T00:00:00&return=DOC&sort=DESC&max=1000"

Haal metadata + document op:

curl -s "https://data.rechtspraak.nl/uitspraken/content?id=ECLI:NL:RVS:2014:1423"

Alleen metadata:

curl -s "https://data.rechtspraak.nl/uitspraken/content?id=ECLI:NL:HR:2014:952&return=META"

Image ophalen:

curl -s -o image.bin "https://data.rechtspraak.nl/uitspraken/image?id=image-identifier-2"


⸻

Implementatietips
	•	Paginer over grote sets met max (≤1000) en from.
	•	Leg retry/backoff in voor stabiliteit; vermijd parallel “hammering”.
	•	Gebruik waardelijst-URI’s i.p.v. losse strings voor creator/subject.
	•	Voor koppelen conclusie ↔ arrest gebruik dcterms:relation met ecli:resourceIdentifier en psi:* attributen.

