# KSeF Pobieracz Faktur

Skrypt w Pythonie, który cyklicznie pobiera faktury (sprzedaży i zakupu) z **Krajowego Systemu e-Faktur (KSeF) API v2**, zapisuje je jako pliki XML i ładuje do bazy **PostgreSQL** w postaci gotowej do raportowania (nagłówki, pozycje, korekty, płatności itd.).

Technicznie: uwierzytelnianie **tokenem KSeF** (nie certyfikatem), pobieranie przez **eksport paczek ZIP** (`/invoices/exports`) z szyfrowaniem AES-256, parser faktur **FA(3)**.

> Skrypt jest narzędziem pomocniczym, nie produktem komercyjnym. Używasz go na własną odpowiedzialność. Przetestuj najpierw na środowisku testowym KSeF.

## Co robi ten skrypt

1. Loguje się do KSeF tokenem i zleca **eksport faktur sprzedaży i zakupu** za ostatnie N dni (domyślnie 7).
2. Pobiera zaszyfrowane paczki, **odszyfrowuje je** i rozpakowuje faktury jako pliki **XML** do katalogów `FA_Sprzedaz/` i `FA_Zakupy/`.
3. **Parsuje każdy nowy XML** (FA(3)) i zapisuje go w PostgreSQL: surowy XML w jednej tabeli oraz dane rozbite na kolumny (nagłówek, pozycje, korekty, płatności, załączniki).
4. Pomija faktury, które już są w bazie, więc można go uruchamiać z crona wiele razy dziennie.

Efekt: masz w SQL aktualną bazę wszystkich faktur z KSeF i możesz robić raporty zwykłym `SELECT`-em, bez ręcznego pobierania plików z portalu.

Dokumentacja szczegółowa: [docs/ARCHITEKTURA.md](docs/ARCHITEKTURA.md) (budowa, kryptografia, diagnostyka) i [docs/MAPOWANIE_FA3.md](docs/MAPOWANIE_FA3.md) (pole XML → kolumna bazy).

## Struktura katalogów

Skrypt przy starcie przechodzi do katalogu, w którym leży (`os.chdir`), więc wszystkie ścieżki poniżej są względne wobec pliku `pobieracz_ksef.py`, niezależnie od tego, skąd go uruchomisz (np. z crona).

```
ksef/                                  ← katalog ze skryptem
├── pobieracz_ksef.py
├── .env                               ← Twoja konfiguracja z tokenem i hasłem (tworzysz sam, nie ma jej w repozytorium)
├── FA_Paczki_ZIP/                     ← surowe paczki po odszyfrowaniu (kopia archiwalna)
│   ├── paczka_FA_Sprzedaz_20261003_060001.zip
│   └── paczka_FA_Zakupy_20261003_060042.zip
├── FA_Sprzedaz/                       ← faktury sprzedaży (eksport „subject1")
│   ├── 2026_09/
│   │   └── <numer-KSeF>.xml
│   ├── 2026_10/
│   │   └── <numer-KSeF>.xml
│   └── Pozostale/                     ← pliki, z których nie dało się odczytać RRRR_MM
└── FA_Zakupy/                         ← faktury zakupu (eksport „subject2")
    └── 2026_10/
        └── <numer-KSeF>.xml
```

Zasady:

- **Nazwa paczki ZIP:** `paczka_<FA_Sprzedaz|FA_Zakupy>_<RRRRMMDD_GGMMSS>.zip`, czyli data i godzina pobrania. Przy dużej liczbie faktur KSeF dzieli paczkę na części, a każda część zapisuje się jako osobny plik.
- **Nazwa pliku XML:** numer KSeF faktury, np. `1234567890-20261003-ABCDEF123456-7A.xml` (format `NIP-RRRRMMDD-HASH-CRC`). Ten numer jest kluczem w bazie (`ksef_pliki_xml.nr_ksef`).
- **Podkatalog `RRRR_MM`** pochodzi z **daty w numerze KSeF** (kiedy faktura trafiła do KSeF), a nie z daty wystawienia na fakturze. Zdarza się, że faktura z końca miesiąca ma numer z początku następnego. Jeśli nazwa nie pasuje do wzorca, plik trafia do `Pozostale/`.
- **Skrypt niczego nie kasuje.** Pliki XML i ZIP-y zostają na dysku po imporcie, więc katalogi rosną. Zaplanuj rotację (np. archiwizacja ZIP-ów starszych niż 90 dni). Źródłem prawdy jest baza, która trzyma pełny XML w `ksef_pliki_xml.plik_xml`.
- **Import czyta katalogi `FA_Sprzedaz` i `FA_Zakupy` rekurencyjnie.** Typ faktury (`S` lub `Z`) ustala po nazwie katalogu głównego. Nie przenoś ręcznie plików między tymi katalogami.
- **Uprawnienia:** katalogi zawierają faktury, czyli dane handlowe i osobowe. Ogranicz do niezbędnych kont (`chmod 700`).
- Katalogi `FA_*` są w `.gitignore`, więc nie trafią do repozytorium.

## Wymagania

- Python 3.9+
- PostgreSQL 9.6+ z klientem `psql` 9.6+ (`schema.sql` używa `JSONB`, `CREATE INDEX IF NOT EXISTS` i `\gexec`)
- Token KSeF wygenerowany w portalu KSeF (uprawnienie do przeglądania/pobierania faktur)

```bash
pip install -r requirements.txt
```

## Instalacja

### 1. Baza danych

```bash
psql -U postgres -v ksef_pass='TWOJE_HASLO' -f schema.sql
```

`schema.sql` tworzy rolę `ksef`, bazę `ksef_ep`, 9 tabel, indeksy i komentarze. Jest idempotentny. Hasło podajesz jako zmienną psql i nie trafia do pliku. Jeśli masz własną bazę/użytkownika, usuń sekcję 1 i dostosuj `\connect`.

### 2. Konfiguracja (zmienne środowiskowe)

Skopiuj `.env.example` do `.env` i uzupełnij. Skrypt czyta konfigurację wyłącznie ze środowiska:

| Zmienna | Wymagana | Opis |
|---|---|---|
| `KSEF_NIP` | tak | NIP firmy (10 cyfr) |
| `KSEF_TOKEN` | tak | token KSeF |
| `DB_PASS` | tak | hasło użytkownika bazy |
| `KSEF_BASE_URL` | nie | domyślnie produkcja `https://api.ksef.mf.gov.pl/v2`; test: `https://api-test.ksef.mf.gov.pl/v2` |
| `KSEF_DNI_WSTECZ` | nie | okno pobierania w dniach (domyślnie 7) |
| `DB_USER`, `DB_HOST`, `DB_PORT`, `DB_NAME` | nie | domyślnie `ksef`, `localhost`, `5432`, `ksef_ep` |

### 3. Uruchomienie

Linux / macOS:

```bash
set -a; . ./.env; set +a
python pobieracz_ksef.py
```

Windows (PowerShell):

```powershell
Get-Content .env | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process')
}
python pobieracz_ksef.py
```

Kod wyjścia: `0` = sukces, `1` = wystąpiły błędy (nadaje się do monitorowania z crona).

### 4. Harmonogram (cron)

```cron
0 6,12,18,23 * * *  cd /opt/ksef && set -a && . ./.env && set +a && python3 pobieracz_ksef.py >> ksef_robot.log 2>&1
```

Okno pobierania to domyślnie ostatnie 7 dni, więc pojedynczy nieudany przebieg sam się nadrabia przy następnym. Plik `.env` powinien mieć prawa `600`.

## Jak to działa

```
        ┌──────────────────────── FAZA 1: KSeF API ────────────────────────┐
        │ 1. POST /auth/challenge             → challenge + timestamp        │
        │ 2. GET  /security/public-key-certificates → klucze RSA MF          │
        │ 3. POST /auth/ksef-token            (token|timestamp, RSA-OAEP)    │
        │ 4. GET  /auth/{ref}  w pętli, aż status.code == 200                │
        │ 5. POST /auth/token/redeem          → accessToken (JWT)            │
        │ 6. POST /invoices/exports  (subject1 = sprzedaż, subject2 = zakup) │
        │ 7. GET  /invoices/exports/{ref} w pętli, aż paczka gotowa          │
        │ 8. pobranie części paczki → odszyfrowanie AES-256-CBC → ZIP → XML  │
        └───────────────────────────────────────────────────────────────────┘
                                   │
                  FA_Sprzedaz/RRRR_MM/*.xml   FA_Zakupy/RRRR_MM/*.xml
                                   │
        ┌──────────────────── FAZA 2: import do PostgreSQL ────────────────┐
        │ parsowanie FA(3) → słowniki → bulk insert partiami po 500 faktur  │
        │ (pomijane są faktury, których nr KSeF już jest w ksef_pliki_xml)  │
        └───────────────────────────────────────────────────────────────────┘
```

### Szczegóły uwierzytelniania i szyfrowania

- Token KSeF jest szyfrowany kluczem publicznym MF (certyfikat z użyciem `KsefTokenEncryption`) algorytmem **RSA-OAEP / SHA-256**. Szyfrowana jest wiadomość `TOKEN|timestampMs`.
- Dla każdego eksportu skrypt losuje świeży klucz AES-256 i IV. Klucz jest szyfrowany RSA-OAEP kluczem MF (`SymmetricKeyEncryption`) i wysyłany w zleceniu eksportu.
- Pobrana paczka jest deszyfrowana **AES-256-CBC** z paddingiem PKCS7. Surowy ZIP jest dodatkowo zachowany w `FA_Paczki_ZIP/`.
- Pliki XML trafiają do `FA_Sprzedaz/` lub `FA_Zakupy/` w podkatalogach `RRRR_MM` (z numeru KSeF).

### ⚠️ Pułapka: `GET /auth/{ref}` zwraca HTTP 200 od razu

W KSeF API v2 odpowiedź HTTP 200 na `GET /auth/{referenceNumber}` oznacza tylko, że *odpytanie się udało*. O zakończeniu uwierzytelniania mówi dopiero **`status.code == 200` w treści odpowiedzi** (`100` = w toku). Skrypt czeka na ten kod (do 60 s). Gdy wykona `redeem` za wcześnie, dostanie błąd `21301`, pusty token i `401` na eksporcie. Objaw jest przerywany (raz działa, raz nie), więc łatwo go pomylić z awarią KSeF.

### Struktura bazy

| Tabela | Zawartość |
|---|---|
| `ksef_pliki_xml` | surowy XML, numer KSeF (unikalny), hash SHA-256, link QR, data pobrania |
| `ksef_naglowki` | nagłówek faktury FA(3): strony (sprzedawca/nabywca), daty, kwoty wg stawek VAT, adnotacje (MPP, odwrotne obciążenie, WNT…), warunki transakcji, płatność, korekty, stopka |
| `ksef_pozycje` | wiersze faktury (`FaWiersz`): indeks, nazwa, ilość, ceny, VAT, GTU, CN, PKWiU |
| `ksef_zamowienia_wiersze` | wiersze zamówienia (faktury zaliczkowe) |
| `ksef_podmioty_trzecie` | `Podmiot3` i `PodmiotUpowazniony` |
| `ksef_faktury_korygowane` | powiązanie korekty z fakturą korygowaną |
| `ksef_faktury_zaliczkowe` | powiązanie faktury rozliczeniowej z zaliczkowymi |
| `ksef_dodatkowe_opisy` | pary klucz/wartość z `DodatkowyOpis` |
| `ksef_zalaczniki` | załączniki jako `JSONB` |

Wszystkie tabele podrzędne wskazują na `ksef_pliki_xml.nr_ksef` (`ON DELETE CASCADE`). Pole `ksef_naglowki.typ_podmiotu` rozróżnia sprzedaż (`S`) i zakup (`Z`). Baza zawiera faktury całego podmiotu, więc przy zakupach warto filtrować po `nip_nabywcy`.

Przykładowe zapytanie, czyli zakupy z ostatniego miesiąca:

```sql
SELECT n.nr_ksef, n.data_wystawienia, n.nazwa_sprzedawcy, p.nazwa_towaru, p.ilosc, p.cena_netto_jedn
FROM ksef_naglowki n
JOIN ksef_pozycje p USING (nr_ksef)
WHERE n.typ_podmiotu = 'Z'
  AND n.rodzaj_faktury = 'VAT'
  AND n.data_wystawienia >= now() - interval '1 month';
```

## Znane ograniczenia

- Zakres dat eksportu jest liczony w **strefie czasowej systemu**, na którym działa skrypt (z poprawnym czasem letnim i zimowym). Serwer powinien mieć ustawioną strefę `Europe/Warsaw`; przy UTC okno będzie przesunięte o 1–2 godziny, co przy oknie 7 dni nie ma praktycznego znaczenia.
- Wywołania HTTP mają limity czasu (10 s na połączenie, 60 s na odpowiedź, 300 s przerwy przy pobieraniu paczki). Chwilowy błąd sieci przy sprawdzaniu statusu paczki jest ponawiany; w pozostałych miejscach kończy przebieg błędem, a następne uruchomienie nadrabia zaległości.
- Kolumna `ksef_naglowki.data_kursu_waluty` jest zarezerwowana i zawsze pusta. Parser zapisuje kurs (`kurs_waluty`), ale nie datę kursu.
- Dane w tabelach, w tym zapisy numerów rachunków i adresów, są wprost z faktur. Chroń bazę jak dane osobowe i handlowe.
- Nazwa paczki ZIP zawiera znacznik czasu z dokładnością do sekundy. Przy paczce złożonej z wielu części pobranych w tej samej sekundzie kopie ZIP mogą się nawzajem nadpisać. Nie wpływa to na import (XML są wypakowywane osobno), tylko na kopię archiwalną.
- Skrypt nie tworzy tabel sam. Użyj `schema.sql`.
- Skrypt nie ma automatycznych testów.

## Bezpieczeństwo

- **Nie commituj** `.env`, tokenu KSeF, haseł ani pobranych faktur (`FA_*`, `*.zip`, `*.xml`). `.gitignore` to blokuje.
- Plik `.env` ustaw na `chmod 600`. Użytkownikowi bazy nadaj minimalne uprawnienia.
- Jeśli token KSeF kiedykolwiek znalazł się w repozytorium lub logu, **unieważnij go w portalu KSeF** i wygeneruj nowy. Samo usunięcie pliku nie wystarczy, bo token zostaje w historii gita.
- Uwaga na `python -m py_compile` i `__pycache__`: bytecode zawiera stałe ze skryptu. Tu sekretów w kodzie nie ma, ale warto zachować nawyk.

## Licencja

[MIT](LICENSE). Możesz używać, kopiować i modyfikować kod, także komercyjnie, pod warunkiem zachowania informacji o prawach autorskich. Oprogramowanie jest dostarczane „tak jak jest", bez gwarancji.
