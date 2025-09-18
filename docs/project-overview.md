# Bedrijfsanalyse API - Project Overview

## Project Beschrijving

Een REST API die automatisch positieve en negatieve berichtgeving over Nederlandse bedrijven verzamelt en analyseert. Het systeem werkt op basis van **bedrijfsnamen** (met optionele KvK-nummers) en combineert AI-gedreven nieuwsanalyse via OpenAI.

## Hoofddoelstellingen

1. **Name-Based Analysis**: Snelle bedrijfsanalyse op basis van bedrijfsnaam
3. **Nederlandse Focus**: Prioriteit voor Nederlandse nieuwsbronnen en contactpersoon analyse
4. **Compliance Ready**: GDPR-compliant zonder data opslag

## Kernfunctionaliteiten

### 1. Company Name Analysis
- Bedrijfsanalyse gebaseerd op bedrijfsnaam (KvK optioneel)
- Contactpersoon integratie in zoekopdrachten
- Nederlandse focus met gestructureerde output

- Categorisatie van juridische issues

### 3. AI-Gedreven Nederlandse Nieuwsanalyse
- OpenAI integration voor Nederlandse nieuwsbronnen
- Prioriteit voor FD, NRC, Volkskrant, NOS, BNR
- Sentiment analyse met positieve/negatieve classificatie
- Contactpersoon mentions in nieuwsartikelen

### 4. Multiple Workflow Endpoints
- **Standard Analysis**: Company name based analysis
- **Nederlandse Analyse**: Dutch-focused analysis
- **Simple Analysis**: Streamlined format with combined results

## Target Users

- **Compliance Officers**: Due diligence processen
- **Credit Managers**: Kredietwaardigheid assessment
- **Business Development**: Partner/klant screening

## Success Criteria

- **Performance**: < 30s response tijd voor standard search
- **Accuracy**: > 85% relevantie score voor gevonden nieuws
- **Compliance**: 100% GDPR compliance, geen data persistentie
- **Reliability**: 99.5% uptime, graceful error handling

## Project Constraints

1. **Geen Data Opslag**: Alle data moet real-time worden opgehaald
2. **Rate Limiting**: Respecteren van API limits van externe services
3. **Compliance**: Respecteren robots.txt, fair use
4. **Performance**: Maximaal 60s voor deep search
5. **Budget**: Minimale OpenAI token usage via efficiënte prompts

## High-Level Architecture

```
Client Request (with company_name + optional kvk_nummer/contactpersoon)
    ↓
FastAPI Application
    ↓
┌─────────────┬─────────────────────────┬─────────────┐
│ KvK Service │ News Service            │ News Service│
│ (optional)  │                         │             │
└─────────────┴─────────────────────────┴─────────────┘
    ↓               ↓                           ↓
KvK API      OpenAI API
(mock/real)      ↓
              Nederlandse bronnen
              (FD, NRC, NOS, etc.)
```

## Project Phases

### Phase 1: Core Infrastructure
- FastAPI setup en basis endpoints
- KvK API integratie
- Request/Response schemas


### Phase 3: AI News Analysis
- OpenAI integration en function calling
- News search en sentiment analyse
- Content filtering en relevantie scoring

### Phase 4: Integration & Testing
- End-to-end testing
- Performance optimization
- Error handling en resilience

### Phase 5: Documentation & Deployment
- API documentatie
- Deployment setup
- Monitoring en logging