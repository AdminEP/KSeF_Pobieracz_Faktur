-- =====================================================================
-- Schemat bazy PostgreSQL dla pobieracza faktur KSeF (pobieracz_ksef.py)
-- Wygenerowany z modeli SQLAlchemy ze skryptu.
--
-- Uzycie (jako superuzytkownik, np. postgres):
--   psql -U postgres -v ksef_pass='TU_WPISZ_HASLO' -f schema.sql
--
-- Skrypt jest idempotentny (IF NOT EXISTS) - mozna go uruchomic ponownie.
-- Haslo przekazywane jest jako zmienna psql i NIE jest zapisane w tym pliku.
-- =====================================================================

-- 1. Uzytkownik aplikacji i baza (pomin, jesli masz wlasne)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ksef') THEN
    CREATE ROLE ksef LOGIN;
  END IF;
END $$;
ALTER ROLE ksef PASSWORD :'ksef_pass';

SELECT 'CREATE DATABASE ksef_ep OWNER ksef ENCODING ''UTF8'''
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'ksef_ep')\gexec

\connect ksef_ep

SET ROLE ksef;

-- 2. Tabele
-- ksef_pliki_xml to tabela nadrzedna: kazda faktura = 1 wiersz (surowy XML + hash + link QR).
-- Pozostale tabele wskazuja na nia przez nr_ksef (ON DELETE CASCADE).

CREATE TABLE IF NOT EXISTS ksef_pliki_xml (
	id SERIAL NOT NULL,
	nazwa_pliku VARCHAR(255) NOT NULL,
	nr_ksef VARCHAR(50) NOT NULL,
	plik_xml TEXT NOT NULL,
	data_pobrania TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
	xml_hash VARCHAR(255),
	url_qr TEXT,
	PRIMARY KEY (id),
	UNIQUE (nr_ksef)
);

CREATE TABLE IF NOT EXISTS ksef_dodatkowe_opisy (
	id SERIAL NOT NULL,
	nr_ksef VARCHAR(50),
	klucz TEXT,
	wartosc TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(nr_ksef) REFERENCES ksef_pliki_xml (nr_ksef) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ksef_faktury_korygowane (
	id SERIAL NOT NULL,
	nr_ksef_korekty VARCHAR(50),
	nr_korygowanej_wewn VARCHAR(255),
	nr_korygowanej_ksef VARCHAR(60),
	data_wyst_korygowanej DATE,
	czy_ksef BOOLEAN,
	PRIMARY KEY (id),
	FOREIGN KEY(nr_ksef_korekty) REFERENCES ksef_pliki_xml (nr_ksef) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ksef_faktury_zaliczkowe (
	id SERIAL NOT NULL,
	nr_ksef_rozliczeniowej VARCHAR(50),
	nr_ksef_zaliczkowej VARCHAR(50),
	PRIMARY KEY (id),
	FOREIGN KEY(nr_ksef_rozliczeniowej) REFERENCES ksef_pliki_xml (nr_ksef) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ksef_naglowki (
	id SERIAL NOT NULL,
	nr_ksef VARCHAR(50),
	kod_formularza VARCHAR(20),
	wariant_formularza VARCHAR(10),
	system_info VARCHAR(255),
	data_wytworzenia_xml TIMESTAMP WITHOUT TIME ZONE,
	miejsce_wystawienia VARCHAR(255),
	data_wystawienia DATE,
	data_sprzedazy DATE,
	okres_fakturowany_od DATE,
	okres_fakturowany_do DATE,
	nr_faktury_wewn VARCHAR(255),
	rodzaj_faktury VARCHAR(50),
	kod_waluty VARCHAR(10),
	znacznik_fp BOOLEAN,
	znacznik_tp BOOLEAN,
	nip_sprzedawcy VARCHAR(50),
	nazwa_sprzedawcy VARCHAR(500),
	adres_sprzedawcy TEXT,
	adres_koresp_sprzedawcy TEXT,
	email_sprzedawcy VARCHAR(255),
	telefon_sprzedawcy VARCHAR(100),
	kraj_sprzedawcy VARCHAR(5),
	nip_nabywcy VARCHAR(50),
	kod_ue_nabywcy VARCHAR(30),
	nr_id_nabywcy VARCHAR(50),
	nazwa_nabywcy VARCHAR(500),
	adres_nabywcy TEXT,
	adres_koresp_nabywcy TEXT,
	nr_klienta VARCHAR(100),
	kraj_nabywcy VARCHAR(5),
	kod_pocztowy_nabywcy VARCHAR(20),
	miejscowosc_nabywcy VARCHAR(255),
	email_nabywcy VARCHAR(255),
	telefon_nabywcy VARCHAR(100),
	czy_jst BOOLEAN,
	czy_grupa_vat BOOLEAN,
	kwota_netto_suma NUMERIC(15, 2),
	kwota_vat_suma NUMERIC(15, 2),
	kwota_brutto_suma NUMERIC(15, 2),
	kwota_do_zaplaty NUMERIC(15, 2),
	wartosc_zamowienia NUMERIC(15, 2),
	kwota_zaliczki_p15zk NUMERIC(15, 2),
	netto_23 NUMERIC(15, 2),
	vat_23 NUMERIC(15, 2),
	vat_23_pln NUMERIC(15, 2),
	netto_8 NUMERIC(15, 2),
	vat_8 NUMERIC(15, 2),
	vat_8_pln NUMERIC(15, 2),
	netto_5 NUMERIC(15, 2),
	vat_5 NUMERIC(15, 2),
	vat_5_pln NUMERIC(15, 2),
	netto_0_eksport NUMERIC(15, 2),
	netto_0_wdt NUMERIC(15, 2),
	netto_0_inne NUMERIC(15, 2),
	netto_zw NUMERIC(15, 2),
	netto_oo NUMERIC(15, 2),
	netto_np NUMERIC(15, 2),
	netto_wnt NUMERIC(15, 2),
	netto_marza NUMERIC(15, 2),
	netto_poza_pl NUMERIC(15, 2),
	netto_odwr_obciazenie NUMERIC(15, 2),
	kurs_waluty NUMERIC(10, 4),
	data_kursu_waluty DATE,
	mpp_p18a BOOLEAN,
	metoda_kasowa_p16 BOOLEAN,
	samofakturowanie_p17 BOOLEAN,
	odwrotne_obciazenie BOOLEAN,
	wnt BOOLEAN,
	nowe_srodki_transportu BOOLEAN,
	procedura_marzy BOOLEAN,
	zwolnienie_vat_podstawa TEXT,
	typ_podmiotu VARCHAR(1),
	nr_umowy VARCHAR(100),
	data_umowy DATE,
	nr_zamowienia VARCHAR(100),
	data_zamowienia DATE,
	nr_partii_towaru VARCHAR(100),
	numery_wz TEXT,
	warunki_dostawy VARCHAR(100),
	rodzaj_transportu VARCHAR(50),
	przewoznik_nip VARCHAR(50),
	przewoznik_nazwa VARCHAR(255),
	termin_platnosci TEXT,
	forma_platnosci TEXT,
	nr_rachunku_bankowego TEXT,
	czy_zaplacono BOOLEAN,
	data_zaplaty DATE,
	kwota_zaplacona NUMERIC(15, 2),
	skonto_kwota NUMERIC(15, 2),
	skonto_warunki TEXT,
	suma_obciazen NUMERIC(15, 2),
	suma_odliczen NUMERIC(15, 2),
	typ_korekty VARCHAR(10),
	przyczyna_korekty TEXT,
	okres_korygowany TEXT,
	korekta_netto NUMERIC(15, 2),
	korekta_vat NUMERIC(15, 2),
	korekta_brutto NUMERIC(15, 2),
	stopka_krs VARCHAR(50),
	stopka_regon VARCHAR(50),
	stopka_bdo VARCHAR(50),
	PRIMARY KEY (id),
	FOREIGN KEY(nr_ksef) REFERENCES ksef_pliki_xml (nr_ksef) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ksef_podmioty_trzecie (
	id SERIAL NOT NULL,
	nr_ksef VARCHAR(50),
	typ_podmiotu VARCHAR(50),
	rola VARCHAR(10),
	nip VARCHAR(50),
	nazwa VARCHAR(500),
	adres TEXT,
	email VARCHAR(255),
	telefon VARCHAR(100),
	udzial NUMERIC(5, 2),
	PRIMARY KEY (id),
	FOREIGN KEY(nr_ksef) REFERENCES ksef_pliki_xml (nr_ksef) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ksef_pozycje (
	id SERIAL NOT NULL,
	nr_ksef VARCHAR(50),
	lp_wiersza INTEGER,
	uuid_wiersza VARCHAR(100),
	indeks_towaru VARCHAR(100),
	data_sprzedazy_wiersza DATE,
	nazwa_towaru VARCHAR(500),
	jm VARCHAR(50),
	ilosc NUMERIC(15, 4),
	cena_netto_jedn NUMERIC(15, 4),
	kwota_rabatu_wiersza NUMERIC(15, 2),
	wartosc_netto_wiersza NUMERIC(15, 2),
	stawka_vat VARCHAR(20),
	kwota_vat_wiersza NUMERIC(15, 2),
	cena_brutto_jedn NUMERIC(15, 4),
	wartosc_brutto_wiersza NUMERIC(15, 2),
	kurs_waluty NUMERIC(10, 4),
	kwota_akcyzy NUMERIC(15, 2),
	stan_pozycji VARCHAR(10),
	gtu VARCHAR(20),
	cn VARCHAR(50),
	pkwiu VARCHAR(50),
	procedura_wiersza VARCHAR(50),
	stawka_vat_oss VARCHAR(20),
	pkob VARCHAR(50),
	PRIMARY KEY (id),
	FOREIGN KEY(nr_ksef) REFERENCES ksef_pliki_xml (nr_ksef) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ksef_zalaczniki (
	id SERIAL NOT NULL,
	nr_ksef VARCHAR(50),
	zawartosc_json JSONB NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(nr_ksef) REFERENCES ksef_pliki_xml (nr_ksef) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ksef_zamowienia_wiersze (
	id SERIAL NOT NULL,
	nr_ksef VARCHAR(50),
	lp_wiersza INTEGER,
	uuid_wiersza VARCHAR(100),
	nazwa_towaru VARCHAR(500),
	jm VARCHAR(50),
	ilosc NUMERIC(15, 4),
	cena_netto_jedn NUMERIC(15, 4),
	kwota_rabatu_wiersza NUMERIC(15, 2),
	wartosc_netto_wiersza NUMERIC(15, 2),
	stawka_vat VARCHAR(20),
	kwota_vat_wiersza NUMERIC(15, 2),
	stan_pozycji VARCHAR(20),
	PRIMARY KEY (id),
	FOREIGN KEY(nr_ksef) REFERENCES ksef_pliki_xml (nr_ksef) ON DELETE CASCADE
);

-- 3. Indeksy (dodatkowe, opcjonalne - skrypt ich nie wymaga, ale przyspieszaja raporty)
CREATE INDEX IF NOT EXISTS ix_naglowki_nr_ksef     ON ksef_naglowki (nr_ksef);
CREATE INDEX IF NOT EXISTS ix_naglowki_data_wyst   ON ksef_naglowki (data_wystawienia);
CREATE INDEX IF NOT EXISTS ix_naglowki_nip_sprz    ON ksef_naglowki (nip_sprzedawcy);
CREATE INDEX IF NOT EXISTS ix_naglowki_nip_nab     ON ksef_naglowki (nip_nabywcy);
CREATE INDEX IF NOT EXISTS ix_naglowki_typ         ON ksef_naglowki (typ_podmiotu);
CREATE INDEX IF NOT EXISTS ix_pozycje_nr_ksef      ON ksef_pozycje (nr_ksef);
CREATE INDEX IF NOT EXISTS ix_pozycje_indeks       ON ksef_pozycje (indeks_towaru);
CREATE INDEX IF NOT EXISTS ix_zam_wiersze_nr_ksef  ON ksef_zamowienia_wiersze (nr_ksef);
CREATE INDEX IF NOT EXISTS ix_podmioty3_nr_ksef    ON ksef_podmioty_trzecie (nr_ksef);
CREATE INDEX IF NOT EXISTS ix_korygowane_nr_ksef   ON ksef_faktury_korygowane (nr_ksef_korekty);
CREATE INDEX IF NOT EXISTS ix_zaliczkowe_nr_ksef   ON ksef_faktury_zaliczkowe (nr_ksef_rozliczeniowej);
CREATE INDEX IF NOT EXISTS ix_opisy_nr_ksef        ON ksef_dodatkowe_opisy (nr_ksef);
CREATE INDEX IF NOT EXISTS ix_zalaczniki_nr_ksef   ON ksef_zalaczniki (nr_ksef);

-- 4. Komentarze
COMMENT ON TABLE  ksef_pliki_xml IS 'Surowe faktury XML pobrane z KSeF (1 wiersz = 1 faktura)';
COMMENT ON TABLE  ksef_naglowki  IS 'Naglowki faktur FA(3) rozlozone na kolumny';
COMMENT ON TABLE  ksef_pozycje   IS 'Wiersze faktur (FaWiersz)';
COMMENT ON COLUMN ksef_naglowki.typ_podmiotu   IS 'S = faktura sprzedazy (eksport subject1), Z = faktura zakupu (subject2)';
COMMENT ON COLUMN ksef_naglowki.rodzaj_faktury IS 'VAT, KOR, ZAL, ROZ, UPR, KOR_ZAL, KOR_ROZ';
COMMENT ON COLUMN ksef_pliki_xml.url_qr        IS 'Link weryfikacyjny QR do portalu KSeF (NIP/data/hash SHA-256 XML)';

RESET ROLE;
