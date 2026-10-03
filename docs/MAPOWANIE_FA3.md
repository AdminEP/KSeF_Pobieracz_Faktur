# Mapowanie pól FA(3) → kolumny bazy

Zestawienie wynika z kodu `parsuj_do_slownikow` i `parsuj_podmiot2`. Ścieżki XML podano względem elementu `Fa` (lub korzenia dokumentu, gdy zaznaczono). Przestrzenie nazw są usuwane przed parsowaniem.

## ksef_pliki_xml

| Kolumna | Źródło |
|---|---|
| `nr_ksef` | nazwa pliku XML (numer KSeF) |
| `nazwa_pliku` | nazwa pliku |
| `plik_xml` | cała treść XML |
| `xml_hash` | SHA-256 XML, base64url bez `=` |
| `url_qr` | `https://qr.ksef.mf.gov.pl/invoice/{NIP sprzedawcy}/{DD-MM-RRRR}/{xml_hash}` |

## ksef_naglowki

| Kolumna | Element XML |
|---|---|
| `kod_formularza`, `wariant_formularza`, `system_info` | `Naglowek/KodFormularza`, `WariantFormularza`, `SystemInfo` |
| `data_wytworzenia_xml` | `Naglowek/DataWytworzeniaFa` (z godziną) |
| `miejsce_wystawienia`, `data_wystawienia`, `data_sprzedazy` | `P_1M`, `P_1`, `P_6` |
| `okres_fakturowany_od/do` | `OkresFa/P_6_Od`, `P_6_Do` |
| `nr_faktury_wewn`, `rodzaj_faktury`, `kod_waluty` | `P_2`, `RodzajFaktury`, `KodWaluty` (domyślnie PLN) |
| `znacznik_fp`, `znacznik_tp` | `FP`, `TP` |
| `nip_sprzedawcy`, `nazwa_sprzedawcy`, `email_`, `telefon_`, `kraj_sprzedawcy` | `Podmiot1/…` |
| `adres_sprzedawcy`, `adres_koresp_sprzedawcy` | `AdresL1` + `AdresL2` z `Adres` / `AdresKoresp` |
| `nip_nabywcy`, `nr_id_nabywcy`, `kod_ue_nabywcy` | `Podmiot2/DaneIdentyfikacyjne/NIP`, `NrID`, `KodUE`+`NrVatUE` (złożone w pełny numer VAT UE) |
| `nazwa_nabywcy`, `nr_klienta`, `email_/telefon_nabywcy` | `Podmiot2/…` |
| `kraj_`, `kod_pocztowy_`, `miejscowosc_nabywcy` | `Podmiot2/Adres/KodKraju`, `KodPocztowy`, `Miejscowosc` |
| `czy_jst`, `czy_grupa_vat` | `Podmiot2/JST`, `GV` |
| `kwota_netto_suma`, `kwota_vat_suma` | suma elementów `P_13_*` i `P_14_*` |
| `kwota_brutto_suma`, `kwota_do_zaplaty` | `P_15`, `Rozliczenie/DoZaplaty` |
| `wartosc_zamowienia`, `kwota_zaliczki_p15zk` | `Zamowienie/WartoscZamowienia`, `P_15ZK` |
| `netto_23/8/5`, `vat_23/8/5`, `vat_*_pln` | `P_13_1..3`, `P_14_1..3`, `P_14_1W..3W` |
| `netto_0_inne/wdt/eksport` | `P_13_6_1`, `P_13_6_2`, `P_13_6_3` |
| `netto_oo`, `netto_np`, `netto_zw` | `P_13_4`, `P_13_5`, `P_13_7` |
| `netto_poza_pl`, `netto_wnt`, `netto_odwr_obciazenie`, `netto_marza` | `P_13_8`, `P_13_9`, `P_13_10`, `P_13_11` |
| `kurs_waluty` | `KursWalutyZ` (faktury zaliczkowe), w pozostałych `KursWaluty` z pierwszego wiersza |
| `data_kursu_waluty` | kolumna zarezerwowana, parser jej nie wypełnia (zawsze `NULL`) |
| `mpp_p18a`, `metoda_kasowa_p16`, `samofakturowanie_p17` | `Adnotacje/P_18A`, `P_16`, `P_17` |
| `odwrotne_obciazenie`, `wnt`, `nowe_srodki_transportu` | `Adnotacje/P_18`, `P_23`, `NoweSrodkiTransportu/P_22` |
| `procedura_marzy` | `Adnotacje/PMarzy/P_PMarzy` (`P_PMarzyN` oznacza „nie”) |
| `zwolnienie_vat_podstawa` | `Adnotacje/Zwolnienie/P_19A` |
| `nr_umowy`, `data_umowy`, `nr_zamowienia`, `data_zamowienia` | `WarunkiTransakcji/Umowy|Zamowienia/…` |
| `nr_partii_towaru`, `warunki_dostawy`, `numery_wz` | `WarunkiTransakcji/NrPartiiTowaru`, `WarunkiDostawy`, elementy `WZ` |
| `rodzaj_transportu`, `przewoznik_nip`, `przewoznik_nazwa` | `Transport/…` |
| `termin_platnosci`, `forma_platnosci`, `nr_rachunku_bankowego` | `Platnosc/TerminPlatnosci/Termin`, `FormaPlatnosci`, `RachunekBankowy/NrRB` + `RachunekBankowyFaktora/NrRB` |
| `czy_zaplacono`, `data_zaplaty`, `kwota_zaplacona` | `Platnosc/Zaplacono`, `DataZaplaty` (lub częściowa), `P_15` lub `ZaplataCzesciowa/KwotaZaplatyCzesciowej` |
| `skonto_kwota`, `skonto_warunki` | `Platnosc/Skonto/…` |
| `suma_obciazen`, `suma_odliczen` | `Rozliczenie/SumaObciazen`, `SumaOdliczen` |
| `typ_korekty`, `przyczyna_korekty`, `okres_korygowany` | `TypKorekty`, `PrzyczynaKorekty`, `OkresFaKorygowanej` |
| `korekta_netto/vat/brutto` | `SumaKorekty/SumaKwotyKorektyNetto|Podatku|Brutto` (korzeń) |
| `stopka_krs/regon/bdo` | `Stopka/Rejestry/KRS|REGON|BDO` |
| `typ_podmiotu` | nadawane przez skrypt: `S` (folder `FA_Sprzedaz`) lub `Z` (`FA_Zakupy`) |

## ksef_pozycje (element `FaWiersz`)

| Kolumna | Element |
|---|---|
| `lp_wiersza`, `uuid_wiersza`, `indeks_towaru` | `NrWierszaFa`, `UU_ID`, `Indeks` |
| `data_sprzedazy_wiersza`, `nazwa_towaru`, `jm` | `P_6A`, `P_7`, `P_8A` |
| `ilosc`, `cena_netto_jedn`, `cena_brutto_jedn` | `P_8B`, `P_9A`, `P_9B` |
| `kwota_rabatu_wiersza`, `wartosc_netto_wiersza`, `wartosc_brutto_wiersza` | `P_10`, `P_11`, `P_11A` |
| `stawka_vat`, `kwota_vat_wiersza`, `stawka_vat_oss` | `P_12`, `P_11Vat`, `P_12_XII` |
| `kurs_waluty`, `kwota_akcyzy`, `procedura_wiersza` | `KursWaluty`, `KwotaAkcyzy`, `Procedura` |
| `gtu`, `cn`, `pkwiu`, `pkob` | `GTU`, `CN`, `PKWiU`, `PKOB` |
| `stan_pozycji` | `PRZED` gdy `StanPrzed`; `PO` dla faktur `KOR`/`KOR_ROZ`; inaczej puste |

## Pozostałe tabele

| Tabela | Element XML |
|---|---|
| `ksef_zamowienia_wiersze` | `ZamowienieWiersz` (`NrWierszaZam`, `UU_IDZ`, `P_7Z`, `P_8AZ`, `P_8BZ`, `P_9AZ`, `P_10Z`, `P_11NettoZ`, `P_12Z`, `P_11VatZ`) |
| `ksef_podmioty_trzecie` | `Podmiot3`, `PodmiotUpowazniony` (rola, NIP, nazwa, adres, kontakt, `Udzial`) |
| `ksef_faktury_korygowane` | `DaneFaKorygowanej` (`NrFaKorygowanej`, `NrKSeFFaKorygowanej`, `DataWystFaKorygowanej`, `NrKSeF`) |
| `ksef_faktury_zaliczkowe` | `FakturaZaliczkowa/NrKSeFFaZaliczkowej` |
| `ksef_dodatkowe_opisy` | `DodatkowyOpis` (`Klucz`, `Wartosc`) |
| `ksef_zalaczniki` | `Zalacznik` jako zagnieżdżony JSON (`JSONB`) |

## Uwagi

- Faktury w walutach obcych: kwoty w nagłówku są w walucie faktury; `kurs_waluty` bierze się z pierwszego wiersza (lub `KursWalutyZ`). Przy analizach kwotowych w PLN przelicz je samodzielnie.
- Korekty (`KOR`, `KOR_ZAL`, `KOR_ROZ`) mają osobne wiersze ze stanem `PRZED`/`PO`. Do cenników i zestawień zakupów zwykle filtruje się `rodzaj_faktury = 'VAT'`.
- Baza zawiera faktury całego podmiotu. Zakupy odfiltrujesz po `typ_podmiotu = 'Z'` i `nip_nabywcy`.
