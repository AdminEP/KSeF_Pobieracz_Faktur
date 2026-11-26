-- Migracja istniejącej bazy (schema.sql sprzed 2026-11-26) do wersji v9 skryptu.
-- Poprawne nazwy kolumn stawek VAT wg broszury MF FA(3), nowe pola płatności i analityczne.
-- Uruchamiać RAZEM z aktualizacją pobieracz_ksef.py (stara wersja skryptu po zmianie nazw
-- kolumn przestanie zapisywać faktury):  psql -U postgres -d ksef_ep -f migracje/2026-11-26_v9.sql
-- Kolumny korekta_netto/vat/brutto i data_kursu_waluty nie są już używane (były zawsze puste);
-- można je usunąć ręcznie.
-- Nowe kolumny dla faktur już zapisanych można uzupełnić z ksef_pliki_xml.plik_xml.

BEGIN;
SET LOCAL lock_timeout = '10s';

-- A. Poprawne nazwy kolumn (broszura MF FA(3), sierpień 2026)
ALTER TABLE ksef_naglowki RENAME COLUMN netto_oo  TO netto_taxi;
ALTER TABLE ksef_naglowki RENAME COLUMN netto_np  TO netto_oss;
ALTER TABLE ksef_naglowki RENAME COLUMN netto_wnt TO netto_uslugi_art100;

ALTER TABLE ksef_naglowki
    ADD COLUMN vat_taxi                    numeric(15,2),
    ADD COLUMN vat_taxi_pln                numeric(15,2),
    ADD COLUMN vat_oss                     numeric(15,2),
-- B. Płatności
    ADD COLUMN ipksef                      varchar(50),
    ADD COLUMN termin_opis                 text,
    ADD COLUMN platnosc_inna               boolean,
    ADD COLUMN opis_platnosci              text,
    ADD COLUMN znacznik_zaplaty_czesciowej varchar(5),
    ADD COLUMN nazwa_banku                 text,
    ADD COLUMN swift                       text,
    ADD COLUMN skonto_wysokosc             text,
-- C. Analityka
    ADD COLUMN waluta_umowna               varchar(3),
    ADD COLUMN kurs_umowny                 numeric(18,6),
    ADD COLUMN nr_fa_korygowany            varchar(255),
    ADD COLUMN stopka_informacje           text;

ALTER TABLE ksef_pozycje
    ADD COLUMN gtin   varchar(20),
    ADD COLUMN zal_15 boolean;

ALTER TABLE ksef_dodatkowe_opisy
    ADD COLUMN nr_wiersza integer;

-- Opisy kolumn: źródło w XML FA(3)
COMMENT ON COLUMN ksef_naglowki.netto_taxi            IS 'P_13_4: sprzedaż netto objęta ryczałtem dla taksówek osobowych (do 2026-11-26 kolumna netto_oo)';
COMMENT ON COLUMN ksef_naglowki.vat_taxi              IS 'P_14_4: podatek od sprzedaży objętej ryczałtem dla taksówek';
COMMENT ON COLUMN ksef_naglowki.vat_taxi_pln          IS 'P_14_4W: podatek z P_14_4 przeliczony na złote (faktury w walucie)';
COMMENT ON COLUMN ksef_naglowki.netto_oss             IS 'P_13_5: sprzedaż netto w procedurze szczególnej OSS (dział XII rozdz. 6a ustawy) (do 2026-11-26 kolumna netto_np)';
COMMENT ON COLUMN ksef_naglowki.vat_oss               IS 'P_14_5: podatek w procedurze OSS';
COMMENT ON COLUMN ksef_naglowki.netto_uslugi_art100   IS 'P_13_9: usługi z art. 100 ust. 1 pkt 4 ustawy (do 2026-11-26 kolumna netto_wnt)';
COMMENT ON COLUMN ksef_naglowki.netto_poza_pl         IS 'P_13_8: dostawa towarów i usługi poza terytorium kraju (bez P_13_5 i P_13_9)';
COMMENT ON COLUMN ksef_naglowki.netto_odwr_obciazenie IS 'P_13_10: odwrotne obciążenie, podatnikiem nabywca';
COMMENT ON COLUMN ksef_naglowki.netto_marza           IS 'P_13_11: procedura marży (art. 119 i 120 ustawy)';
COMMENT ON COLUMN ksef_naglowki.kwota_vat_suma        IS 'Suma pól P_14_x w walucie faktury, bez P_14_xW (od v9; wcześniej w fakturach walutowych zawyżona o VAT w PLN)';
COMMENT ON COLUMN ksef_naglowki.ipksef                IS 'Platnosc/IPKSeF: identyfikator płatności KSeF';
COMMENT ON COLUMN ksef_naglowki.termin_opis           IS 'Platnosc/TerminPlatnosci/TerminOpis: ilość, jednostka, zdarzenie początkowe';
COMMENT ON COLUMN ksef_naglowki.platnosc_inna         IS 'Platnosc/PlatnoscInna: inna forma płatności';
COMMENT ON COLUMN ksef_naglowki.opis_platnosci        IS 'Platnosc/OpisPlatnosci: opis innej formy płatności';
COMMENT ON COLUMN ksef_naglowki.znacznik_zaplaty_czesciowej IS 'Platnosc/ZnacznikZaplatyCzesciowej';
COMMENT ON COLUMN ksef_naglowki.nazwa_banku           IS 'Platnosc/RachunekBankowy(Faktora)/NazwaBanku, kolejność jak nr_rachunku_bankowego';
COMMENT ON COLUMN ksef_naglowki.swift                 IS 'Platnosc/RachunekBankowy(Faktora)/SWIFT, kolejność jak nr_rachunku_bankowego';
COMMENT ON COLUMN ksef_naglowki.skonto_wysokosc       IS 'Platnosc/Skonto/WysokoscSkonta (tekst z faktury)';
COMMENT ON COLUMN ksef_naglowki.waluta_umowna         IS 'WarunkiTransakcji/WalutaUmowna';
COMMENT ON COLUMN ksef_naglowki.kurs_umowny           IS 'WarunkiTransakcji/KursUmowny';
COMMENT ON COLUMN ksef_naglowki.nr_fa_korygowany      IS 'Fa/NrFaKorygowany: poprawny numer faktury korygowanej';
COMMENT ON COLUMN ksef_naglowki.stopka_informacje     IS 'Stopka/Informacje/StopkaFaktury';
COMMENT ON COLUMN ksef_pozycje.gtin                   IS 'FaWiersz/GTIN';
COMMENT ON COLUMN ksef_pozycje.zal_15                 IS 'FaWiersz/P_12_Zal_15: towar lub usługa z załącznika 15 (MPP)';
COMMENT ON COLUMN ksef_dodatkowe_opisy.nr_wiersza     IS 'DodatkowyOpis/NrWiersza: numer wiersza faktury, którego dotyczy opis';

CREATE INDEX IF NOT EXISTS ix_pozycje_gtin ON ksef_pozycje (gtin) WHERE gtin IS NOT NULL;

COMMIT;
