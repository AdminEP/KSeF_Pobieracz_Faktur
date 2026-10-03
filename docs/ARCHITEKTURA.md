# Architektura i działanie skryptu

Dokument opisuje budowę `pobieracz_ksef.py` dla osób, które chcą go zrozumieć, uruchomić na własnym środowisku lub rozwijać.

## 1. Cel

Skrypt automatyzuje pobieranie faktur ustrukturyzowanych (FA(3)) z KSeF i utrzymuje ich lustro w PostgreSQL:

- **wejście:** token KSeF + NIP firmy,
- **wyjście:** pliki XML na dysku oraz rozbite na kolumny dane w bazie (nagłówki, pozycje, korekty, płatności, załączniki).

Typowe zastosowania: raporty zakupowe i sprzedażowe w SQL, kontrola cen dostawców, uzgadnianie z ERP, archiwum XML.

## 2. Struktura pliku `pobieracz_ksef.py`

| Sekcja | Zawartość |
|---|---|
| 1. Konfiguracja | zmienne środowiskowe, okno dat (`DATA_OD_DT`/`DATA_DO_DT`) |
| 2. Modele bazy | klasy SQLAlchemy odpowiadające tabelom (źródło prawdy dla `schema.sql`) |
| 3. Funkcje KSeF API | uwierzytelnianie, eksport, śledzenie statusu, pobranie i deszyfrowanie paczki |
| 4. Parser XML | funkcje pomocnicze (`text_of`, `float_of`, `date_of`…) i `parsuj_podmiot2` |
| `parsuj_do_slownikow` | zamiana jednego XML na słowniki gotowe do `bulk_insert_mappings` |
| 5. Zapis do PostgreSQL | `zaladuj_do_postgresql` — wsady po 500 faktur |
| 6. Główny proces | `main_combo` — kolejność faz, log, kod wyjścia |

## 3. Przebieg wykonania

1. **Uwierzytelnienie** (`pobierz_wyzwanie` → `pobierz_klucze_rsa` → `autoryzuj_sie` → `pobierz_token_jwt`).
2. **Eksport sprzedaży** (`subject1`) i **zakupów** (`subject2`) dla okna dat — `inicjuj_eksport_zip`.
3. **Oczekiwanie na paczkę** — `sledz_status_i_pobierz`, odpytywanie co 10 s, limit 30 minut.
4. **Pobranie i deszyfrowanie** — `pobierz_i_odszyfruj`: AES-256-CBC, usunięcie paddingu PKCS7, zapis ZIP w `FA_Paczki_ZIP/`, wypakowanie XML do `FA_Sprzedaz/` lub `FA_Zakupy/` (podkatalogi `RRRR_MM`).
5. **Import** — `zaladuj_do_postgresql` przechodzi po plikach XML, pomija te, których numer KSeF jest już w `ksef_pliki_xml`, parsuje resztę i zapisuje partiami.
6. **Podsumowanie** — log z czasem trwania; kod wyjścia `1`, jeśli którykolwiek etap się nie powiódł.

Numer KSeF faktury = nazwa pliku XML bez rozszerzenia. To on jest kluczem deduplikacji.

### Pliki na dysku

Skrypt wykonuje `os.chdir` do katalogu, w którym leży, więc poniższe ścieżki są zawsze względne wobec niego.

| Ścieżka | Tworzy | Zawartość |
|---|---|---|
| `FA_Paczki_ZIP/paczka_<FA_Sprzedaz\|FA_Zakupy>_<RRRRMMDD_GGMMSS>.zip` | `pobierz_i_odszyfruj` | odszyfrowana paczka (kopia archiwalna); osobny plik dla każdej części paczki |
| `FA_Sprzedaz/<RRRR_MM>/<numer-KSeF>.xml` | `pobierz_i_odszyfruj` | faktury sprzedaży |
| `FA_Zakupy/<RRRR_MM>/<numer-KSeF>.xml` | `pobierz_i_odszyfruj` | faktury zakupu |
| `FA_*/Pozostale/` | `pobierz_i_odszyfruj` | XML, z których nie odczytano `RRRR_MM` z nazwy |

`RRRR_MM` jest brane z drugiego segmentu nazwy pliku rozdzielonej myślnikami (`NIP-RRRRMMDD-HASH-CRC.xml`), czyli z daty nadania numeru KSeF, a nie z daty wystawienia (`P_1`). Skrypt nie usuwa plików po imporcie. Kolejne uruchomienia nadpisują ten sam plik XML, jeśli faktura trafi do paczki ponownie (okno dat się nakłada), ale do bazy wchodzi tylko raz.

## 4. Kryptografia

| Element | Mechanizm |
|---|---|
| Token KSeF | RSA-OAEP (SHA-256, MGF1-SHA-256) kluczem publicznym MF o zastosowaniu `KsefTokenEncryption`; szyfrowana jest wiadomość `token\|timestampMs` |
| Klucz sesji eksportu | losowy 32-bajtowy klucz AES + 16-bajtowy IV na każdy eksport; klucz szyfrowany RSA-OAEP kluczem `SymmetricKeyEncryption` |
| Paczka z KSeF | AES-256-CBC, PKCS7 |
| Hash faktury | SHA-256 surowego XML, zapis jako base64url bez paddingu (`xml_hash`), używany w linku QR |

Klucze publiczne MF są pobierane przy każdym uruchomieniu z `/security/public-key-certificates`. Nic nie jest zaszyte w kodzie.

## 5. Model danych

```
ksef_pliki_xml (nr_ksef UNIQUE)
   ├── ksef_naglowki              1:1   nagłówek FA(3)
   ├── ksef_pozycje               1:N   FaWiersz
   ├── ksef_zamowienia_wiersze    1:N   ZamowienieWiersz (zaliczki)
   ├── ksef_podmioty_trzecie      1:N   Podmiot3, PodmiotUpowazniony
   ├── ksef_faktury_korygowane    1:N   DaneFaKorygowanej
   ├── ksef_faktury_zaliczkowe    1:N   FakturaZaliczkowa
   ├── ksef_dodatkowe_opisy       1:N   DodatkowyOpis
   └── ksef_zalaczniki            0..1  Zalacznik (JSONB)
```

Pełne mapowanie pól XML → kolumn: [MAPOWANIE_FA3.md](MAPOWANIE_FA3.md).

## 6. Decyzje projektowe

- **Surowy XML jest zawsze zachowany** (`ksef_pliki_xml.plik_xml`). Jeśli parser czegoś nie obejmuje albo zmieni się schemat, można przeliczyć kolumny bez ponownego pobierania z KSeF.
- **Idempotencja zamiast stanu.** Skrypt nie zapamiętuje „ostatniej daty”. Za każdym razem pobiera okno (domyślnie 7 dni) i pomija duplikaty. Pojedyncze nieudane uruchomienie nie gubi faktur.
- **Partie po 500 faktur** w jednej transakcji. Błąd wsadu powoduje `rollback` tylko tej partii; wsad jest ponawiany przy następnym uruchomieniu, bo faktury nie trafiły do bazy.
- **Kwoty jako `Numeric`**, ceny jednostkowe z 4 miejscami po przecinku.
- **Limity czasu.** Każde wywołanie HTTP ma `timeout` (`HTTP_TIMEOUT` = 10 s na połączenie i 60 s na odpowiedź; `HTTP_TIMEOUT_POBRANIE` = 300 s przerwy między porcjami danych paczki). Oczekiwanie na paczkę ma dodatkowo limit 30 minut, a błąd sieci w tej pętli jest ponawiany zamiast przerywać przebieg.
- **Daty w strefie systemowej.** `data_dla_ksef` dokleja do daty przesunięcie strefy właściwe dla danego dnia, więc czas letni i zimowy są obsłużone bez stałej `+01:00`.
- **Adres paczki nie trafia do logu.** Przy błędzie pobierania logowany jest tylko typ wyjątku, bo jego treść zawiera podpisany adres do pobrania.
- **Kod wyjścia** odzwierciedla wynik, więc cron i monitoring mogą reagować na błędy.

## 7. Rozbudowa

- **Inny harmonogram lub zakres dat:** `KSEF_DNI_WSTECZ` albo ustaw `DATA_OD_DT`/`DATA_DO_DT` na sztywno (zakomentowana „Opcja A” w sekcji 1).
- **Nowe pole z faktury:** dodaj kolumnę w modelu (sekcja 2), wpis w `naglowek_dict` lub `pozycje_lista` (`parsuj_do_slownikow`) i `ALTER TABLE` w bazie. Starsze faktury można uzupełnić ponownie przez parser z zapisanego `plik_xml`.
- **Środowisko testowe:** `KSEF_BASE_URL=https://api-test.ksef.mf.gov.pl/v2`.

## 8. Diagnostyka

| Objawy | Przyczyna / działanie |
|---|---|
| `401` na `/invoices/exports` zaraz po „Sesja uwierzytelniona” | pusty `accessToken`; sprawdź `status.code` z `GET /auth/{ref}` (patrz README), a nie awarię KSeF |
| `21301 Status uwierzytelniania (100)…` | `redeem` wywołany przed końcem uwierzytelniania; skrypt czeka na `status.code == 200` |
| „Błąd logowania do API KSeF. Sprawdź NIP i Token.” | zły NIP, token lub środowisko (produkcja kontra test) |
| „Przekroczono limit 30 min” | paczka dużej firmy bywa generowana długo; zmniejsz `KSEF_DNI_WSTECZ` |
| „Brak wymaganych zmiennych środowiskowych: …” | nie wczytano `.env` przed uruchomieniem albo brakuje w nim wymienionych zmiennych; zob. `.env.example` |
| „Problem z połączeniem przy sprawdzaniu statusu” | chwilowy błąd sieci; skrypt ponawia do limitu 30 minut |
| „błąd krytyczny: … Timeout / ConnectionError” | KSeF nie odpowiedział w limicie czasu; następny przebieg nadrobi okno |
| `relation "ksef_naglowki" does not exist` | nie uruchomiono `schema.sql` |
| „Błąd zapisu wsadu” w logu | szczegóły w treści wyjątku; wsad zostanie ponowiony następnym razem |
