import os
import io
import sys
import time
import traceback
import base64
import hashlib
import zipfile
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.backends import default_backend
from cryptography import x509

from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, Numeric, Text, Boolean, ForeignKey, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.dialects.postgresql import JSONB

# ==========================================
# 1. KONFIGURACJA GŁÓWNA
# ==========================================
_WYMAGANE = ("KSEF_NIP", "KSEF_TOKEN", "DB_PASS")
_brakujace = [z for z in _WYMAGANE if not os.environ.get(z)]
if _brakujace:
    sys.exit(f"❌ Brak wymaganych zmiennych środowiskowych: {', '.join(_brakujace)}. "
             f"Uzupełnij plik .env (wzór: .env.example) i wczytaj go przed uruchomieniem.")

NIP_FIRMY     = os.environ["KSEF_NIP"]             # NIP firmy (10 cyfr, bez kresek)
TOKEN_KSEF_V2 = os.environ["KSEF_TOKEN"]           # token KSeF wygenerowany w portalu KSeF

DB_USER = os.environ.get("DB_USER", "ksef")
DB_PASS = os.environ["DB_PASS"]
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "ksef_ep")

# Środowisko KSeF: https://api.ksef.mf.gov.pl/v2 (produkcja), https://api-test.ksef.mf.gov.pl/v2 (test)
BASE_URL = os.environ.get("KSEF_BASE_URL", "https://api.ksef.mf.gov.pl/v2")

# Opcja A — sztywny zakres dat
#DATA_OD_DT = datetime.strptime("2026-05-20", "%Y-%m-%d")
#DATA_DO_DT  = datetime.strptime("2026-06-04", "%Y-%m-%d")

# Opcja B — automatyczne daty (odkomentuj dla Crona):
DATA_DO_DT = datetime.now()
DATA_OD_DT = DATA_DO_DT - timedelta(days=int(os.environ.get("KSEF_DNI_WSTECZ", "7")))

# Limity czasu wywołań HTTP w sekundach: (nawiązanie połączenia, oczekiwanie na dane).
# Limit odczytu dotyczy przerwy między kolejnymi porcjami danych, a nie całego pobierania.
HTTP_TIMEOUT          = (10, 60)
HTTP_TIMEOUT_POBRANIE = (10, 300)

def data_dla_ksef(dt):
    """Data w ISO 8601 z przesunięciem strefy systemowej właściwym dla tej daty (czas letni/zimowy)."""
    return dt.astimezone().isoformat(timespec="seconds")

sciezka_skryptu = os.path.dirname(os.path.abspath(__file__))
os.chdir(sciezka_skryptu)


# ==========================================
# 2. MODELE BAZY DANYCH (SQLAlchemy)
# ==========================================
# URL.create zamiast f-stringa: haslo ze znakami specjalnymi (@ : / %) nie psuje adresu polaczenia
DATABASE_URI = URL.create("postgresql+psycopg2", username=DB_USER, password=DB_PASS,
                          host=DB_HOST, port=int(DB_PORT), database=DB_NAME)
engine = create_engine(DATABASE_URI, echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

class KsefPlikXml(Base):
    __tablename__ = 'ksef_pliki_xml'
    id           = Column(Integer, primary_key=True, autoincrement=True)
    nazwa_pliku  = Column(String(255), nullable=False)
    nr_ksef      = Column(String(50), unique=True, nullable=False)
    plik_xml     = Column(Text, nullable=False)
    data_pobrania = Column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    xml_hash     = Column(String(255))
    url_qr       = Column(Text)

class KsefNaglowek(Base):
    __tablename__ = 'ksef_naglowki'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nr_ksef = Column(String(50), ForeignKey('ksef_pliki_xml.nr_ksef', ondelete='CASCADE'))
    kod_formularza         = Column(String(20))
    wariant_formularza     = Column(String(10))
    system_info            = Column(String(255))
    data_wytworzenia_xml   = Column(DateTime)
    miejsce_wystawienia    = Column(String(255))
    data_wystawienia       = Column(Date)
    data_sprzedazy         = Column(Date)
    okres_fakturowany_od   = Column(Date)
    okres_fakturowany_do   = Column(Date)
    nr_faktury_wewn        = Column(String(255))
    rodzaj_faktury         = Column(String(50))
    kod_waluty             = Column(String(10), default='PLN')
    znacznik_fp            = Column(Boolean, default=False)
    znacznik_tp            = Column(Boolean, default=False)
    nip_sprzedawcy         = Column(String(50))
    nazwa_sprzedawcy       = Column(String(500))
    adres_sprzedawcy       = Column(Text)
    adres_koresp_sprzedawcy = Column(Text)
    email_sprzedawcy       = Column(String(255))
    telefon_sprzedawcy     = Column(String(100))
    kraj_sprzedawcy        = Column(String(5))    # KodKraju z Podmiot1//Adres
    nip_nabywcy            = Column(String(50))
    kod_ue_nabywcy         = Column(String(30))   # pełny NrVatUE np. HU10949315
    nr_id_nabywcy          = Column(String(50))
    nazwa_nabywcy          = Column(String(500))
    adres_nabywcy          = Column(Text)
    adres_koresp_nabywcy   = Column(Text)
    nr_klienta             = Column(String(100))
    kraj_nabywcy           = Column(String(5))    # KodKraju z Podmiot2//Adres
    kod_pocztowy_nabywcy   = Column(String(20))
    miejscowosc_nabywcy    = Column(String(255))
    email_nabywcy          = Column(String(255))
    telefon_nabywcy        = Column(String(100))
    czy_jst                = Column(Boolean, default=False)
    czy_grupa_vat          = Column(Boolean, default=False)
    kwota_netto_suma       = Column(Numeric(15, 2))
    kwota_vat_suma         = Column(Numeric(15, 2))
    kwota_brutto_suma      = Column(Numeric(15, 2))
    kwota_do_zaplaty       = Column(Numeric(15, 2))
    wartosc_zamowienia     = Column(Numeric(15, 2))
    kwota_zaliczki_p15zk   = Column(Numeric(15, 2))
    netto_23 = Column(Numeric(15,2)); vat_23 = Column(Numeric(15,2)); vat_23_pln = Column(Numeric(15,2))
    netto_8  = Column(Numeric(15,2)); vat_8  = Column(Numeric(15,2)); vat_8_pln  = Column(Numeric(15,2))
    netto_5  = Column(Numeric(15,2)); vat_5  = Column(Numeric(15,2)); vat_5_pln  = Column(Numeric(15,2))
    netto_0_eksport = Column(Numeric(15,2))
    netto_0_wdt     = Column(Numeric(15,2))
    netto_0_inne    = Column(Numeric(15,2))
    netto_zw  = Column(Numeric(15,2))
    netto_oo  = Column(Numeric(15,2))
    netto_np  = Column(Numeric(15,2))
    netto_wnt  = Column(Numeric(15,2))
    netto_marza = Column(Numeric(15,2))
    netto_poza_pl         = Column(Numeric(15,2))  # P_13_8: usługi poza PL (nie OSS, nie art.100)
    netto_odwr_obciazenie = Column(Numeric(15,2))  # P_13_10: odwrotne obciążenie krajowe kwota
    kurs_waluty           = Column(Numeric(10, 4))  # kurs waluty faktury (dla EUR itp.)
    data_kursu_waluty     = Column(Date)            # data kursu waluty
    mpp_p18a              = Column(Boolean, default=False)
    metoda_kasowa_p16     = Column(Boolean, default=False)
    samofakturowanie_p17  = Column(Boolean, default=False)
    odwrotne_obciazenie   = Column(Boolean, default=False)  # P_18=1
    wnt                   = Column(Boolean, default=False)  # P_23=1 WNT
    nowe_srodki_transportu = Column(Boolean, default=False) # P_22=1
    procedura_marzy       = Column(Boolean, default=False)
    zwolnienie_vat_podstawa = Column(Text)
    typ_podmiotu          = Column(String(1))  # S=sprzedaż, Z=zakup
    nr_umowy           = Column(String(100))
    data_umowy         = Column(Date)
    nr_zamowienia      = Column(String(100))
    data_zamowienia    = Column(Date)
    nr_partii_towaru   = Column(String(100))
    numery_wz          = Column(Text)
    warunki_dostawy    = Column(String(100))
    rodzaj_transportu  = Column(String(50))
    przewoznik_nip     = Column(String(50))
    przewoznik_nazwa   = Column(String(255))
    termin_platnosci   = Column(Text)
    forma_platnosci    = Column(Text)
    nr_rachunku_bankowego = Column(Text)
    czy_zaplacono      = Column(Boolean, default=False)
    data_zaplaty       = Column(Date)
    kwota_zaplacona    = Column(Numeric(15,2))
    skonto_kwota       = Column(Numeric(15,2))
    skonto_warunki     = Column(Text)
    suma_obciazen      = Column(Numeric(15,2))
    suma_odliczen      = Column(Numeric(15,2))
    typ_korekty        = Column(String(10))
    przyczyna_korekty  = Column(Text)
    okres_korygowany   = Column(Text)
    korekta_netto      = Column(Numeric(15,2))
    korekta_vat        = Column(Numeric(15,2))
    korekta_brutto     = Column(Numeric(15,2))
    stopka_krs   = Column(String(50))
    stopka_regon = Column(String(50))
    stopka_bdo   = Column(String(50))

class KsefPozycja(Base):
    __tablename__ = 'ksef_pozycje'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nr_ksef              = Column(String(50), ForeignKey('ksef_pliki_xml.nr_ksef', ondelete='CASCADE'))
    lp_wiersza           = Column(Integer)
    uuid_wiersza         = Column(String(100))
    indeks_towaru        = Column(String(100))
    data_sprzedazy_wiersza = Column(Date)
    nazwa_towaru         = Column(String(500))
    jm                   = Column(String(50))
    ilosc                = Column(Numeric(15,4))
    cena_netto_jedn      = Column(Numeric(15,4))
    kwota_rabatu_wiersza = Column(Numeric(15,2))
    wartosc_netto_wiersza = Column(Numeric(15,2))
    stawka_vat           = Column(String(20))
    kwota_vat_wiersza    = Column(Numeric(15,2))
    cena_brutto_jedn     = Column(Numeric(15,4))
    wartosc_brutto_wiersza = Column(Numeric(15,2))
    kurs_waluty          = Column(Numeric(10,4))
    kwota_akcyzy         = Column(Numeric(15,2))
    stan_pozycji         = Column(String(10))
    gtu                  = Column(String(20))
    cn                   = Column(String(50))
    pkwiu                = Column(String(50))
    procedura_wiersza    = Column(String(50))
    stawka_vat_oss       = Column(String(20))  # P_12_XII: stawka VAT OSS w kraju nabywcy
    pkob                 = Column(String(50))  # PKOB: klasyfikacja budowlana

class KsefZamowienieWiersz(Base):
    __tablename__ = 'ksef_zamowienia_wiersze'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nr_ksef              = Column(String(50), ForeignKey('ksef_pliki_xml.nr_ksef', ondelete='CASCADE'))
    lp_wiersza           = Column(Integer)
    uuid_wiersza         = Column(String(100))
    nazwa_towaru         = Column(String(500))
    jm                   = Column(String(50))
    ilosc                = Column(Numeric(15,4))
    cena_netto_jedn      = Column(Numeric(15,4))
    kwota_rabatu_wiersza = Column(Numeric(15,2))
    wartosc_netto_wiersza = Column(Numeric(15,2))
    stawka_vat           = Column(String(20))
    kwota_vat_wiersza    = Column(Numeric(15,2))
    stan_pozycji         = Column(String(20))

class KsefPodmiotTrzeci(Base):
    __tablename__ = 'ksef_podmioty_trzecie'
    id            = Column(Integer, primary_key=True, autoincrement=True)
    nr_ksef       = Column(String(50), ForeignKey('ksef_pliki_xml.nr_ksef', ondelete='CASCADE'))
    typ_podmiotu  = Column(String(50))
    rola          = Column(String(10))
    nip           = Column(String(50))
    nazwa         = Column(String(500))
    adres         = Column(Text)
    email         = Column(String(255))
    telefon       = Column(String(100))
    udzial        = Column(Numeric(5,2))

class KsefFakturaKorygowana(Base):
    __tablename__ = 'ksef_faktury_korygowane'
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    nr_ksef_korekty     = Column(String(50), ForeignKey('ksef_pliki_xml.nr_ksef', ondelete='CASCADE'))
    nr_korygowanej_wewn = Column(String(255))
    nr_korygowanej_ksef = Column(String(60))
    data_wyst_korygowanej = Column(Date)
    czy_ksef            = Column(Boolean, default=True)  # TRUE=była w KSeF, FALSE=poza KSeF

class KsefFakturaZaliczkowa(Base):
    __tablename__ = 'ksef_faktury_zaliczkowe'
    id                       = Column(Integer, primary_key=True, autoincrement=True)
    nr_ksef_rozliczeniowej   = Column(String(50), ForeignKey('ksef_pliki_xml.nr_ksef', ondelete='CASCADE'))
    nr_ksef_zaliczkowej      = Column(String(50))

class KsefDodatkowyOpis(Base):
    __tablename__ = 'ksef_dodatkowe_opisy'
    id      = Column(Integer, primary_key=True, autoincrement=True)
    nr_ksef = Column(String(50), ForeignKey('ksef_pliki_xml.nr_ksef', ondelete='CASCADE'))
    klucz   = Column(Text)
    wartosc = Column(Text)

class KsefZalacznik(Base):
    __tablename__ = 'ksef_zalaczniki'
    id             = Column(Integer, primary_key=True, autoincrement=True)
    nr_ksef        = Column(String(50), ForeignKey('ksef_pliki_xml.nr_ksef', ondelete='CASCADE'))
    zawartosc_json = Column(JSONB, nullable=False)


# ==========================================
# 3. FUNKCJE KSeF API
# ==========================================
def pobierz_wyzwanie():
    print("   🔑 Pobieranie wyzwania autoryzacyjnego...")
    r = requests.post(f"{BASE_URL}/auth/challenge", json={}, timeout=HTTP_TIMEOUT)
    if r.status_code in [200, 201]:
        return r.json()['challenge'], r.json()['timestampMs']
    raise Exception("Błąd pobierania wyzwania API KSeF.")

def pobierz_klucze_rsa():
    print("   🔐 Pobieranie kluczy certyfikatów MF...")
    klucz_auth = klucz_aes = None
    r = requests.get(f"{BASE_URL}/security/public-key-certificates", timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        for cert in r.json():
            cert_str = cert.get("certificate") or cert.get("encodedCertificate")
            if "-----BEGIN" in cert_str:
                cert_obj = x509.load_pem_x509_certificate(cert_str.encode(), default_backend())
            else:
                cert_obj = x509.load_der_x509_certificate(base64.b64decode(cert_str), default_backend())
            if "KsefTokenEncryption" in cert.get("usage", []):    klucz_auth = cert_obj.public_key()
            if "SymmetricKeyEncryption" in cert.get("usage", []):  klucz_aes  = cert_obj.public_key()
    return klucz_auth, klucz_aes

def autoryzuj_sie(nip, challenge, timestamp_ms, klucz_auth):
    print(f"   🛡️  Autoryzacja tokenem dla NIP {nip}...")
    wiadomosc = f"{TOKEN_KSEF_V2}|{timestamp_ms}".encode('utf-8')
    zaszyfrowane = klucz_auth.encrypt(
        wiadomosc,
        rsa_padding.OAEP(mgf=rsa_padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    payload = {
        "challenge": challenge,
        "contextIdentifier": {"type": "Nip", "value": nip},
        "encryptedToken": base64.b64encode(zaszyfrowane).decode('utf-8')
    }
    r = requests.post(f"{BASE_URL}/auth/ksef-token", json=payload, timeout=HTTP_TIMEOUT)
    if r.status_code in [200, 201, 202]:
        data = r.json()
        return data['referenceNumber'], data.get('authenticationToken', {}).get('token', data.get('authenticationToken'))
    raise Exception("Błąd logowania do API KSeF. Sprawdź NIP i Token.")

def pobierz_token_jwt(nr_ref, auth_token):
    # HTTP 200 znaczy tylko "odpytanie sie udalo" - o zakonczeniu uwierzytelniania
    # mowi dopiero status.code == 200 w tresci odpowiedzi (100 = w toku).
    naglowki = {"Authorization": f"Bearer {auth_token}"}
    for _ in range(30):
        r = requests.get(f"{BASE_URL}/auth/{nr_ref}", headers=naglowki, timeout=HTTP_TIMEOUT)
        if r.status_code == 200:
            status = r.json().get("status", {})
            kod = status.get("code")
            if kod == 200:
                break
            if kod not in (100, 199):
                raise Exception(f"Uwierzytelnianie odrzucone przez KSeF (status {kod}): {status.get('description')}")
        time.sleep(2)
    else:
        raise Exception("Uwierzytelnianie w KSeF nie zakonczylo sie w ciagu 60 s.")

    r = requests.post(f"{BASE_URL}/auth/token/redeem",
                      headers={"Authorization": f"Bearer {auth_token}", "Accept": "application/json"},
                      timeout=HTTP_TIMEOUT)
    if r.status_code not in (200, 201):
        raise Exception(f"Blad pobierania accessToken (HTTP {r.status_code}): {r.text[:300]}")
    token = r.json().get('accessToken', {}).get('token', r.json().get('accessToken'))
    if not token:
        raise Exception(f"KSeF nie zwrocil accessToken: {r.text[:300]}")
    return token

def inicjuj_eksport_zip(access_token, typ_podmiotu, nazwa_wyswietlana, klucz_rsa_aes):
    aes_key = os.urandom(32)
    iv      = os.urandom(16)
    zaszyfrowany_klucz_aes = klucz_rsa_aes.encrypt(
        aes_key,
        rsa_padding.OAEP(mgf=rsa_padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    payload = {
        "filters": {
            "subjectType": typ_podmiotu,
            "dateRange": {
                "dateType": "invoicing",
                "from": data_dla_ksef(DATA_OD_DT),
                "to":   data_dla_ksef(DATA_DO_DT)
            }
        },
        "encryption": {
            "encryptedSymmetricKey": base64.b64encode(zaszyfrowany_klucz_aes).decode('utf-8'),
            "initializationVector":  base64.b64encode(iv).decode('utf-8')
        }
    }
    print(f"\n   📡 Zlecam eksport paczki {nazwa_wyswietlana}...")
    r = requests.post(f"{BASE_URL}/invoices/exports",
                      headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                      json=payload, timeout=HTTP_TIMEOUT)
    if r.status_code in [200, 201, 202]:
        nr_ref = r.json().get('referenceNumber')
        print(f"   ✅ Zlecenie przyjęte. ID: {nr_ref}")
        return nr_ref, aes_key, iv
    print(f"   ❌ Błąd zlecenia: {r.text}")
    return None, None, None

def pobierz_i_odszyfruj(url, aes_key, iv, bazowy_folder):
    print("   📥 Pobieranie zaszyfrowanej paczki ZIP...")
    try:
        r = requests.get(url, stream=True, timeout=HTTP_TIMEOUT_POBRANIE)
        zaszyfrowane_bajty = r.content if r.status_code == 200 else None
    except requests.RequestException as e:
        # sam typ błędu: treść wyjątku zawiera podpisany adres paczki, który nie powinien trafić do logu
        print(f"   ❌ Błąd pobierania paczki: {type(e).__name__}")
        return False
    if r.status_code != 200:
        print(f"   ❌ Błąd pobierania paczki: HTTP {r.status_code}")
        return False
    cipher   = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded    = decryptor.update(zaszyfrowane_bajty) + decryptor.finalize()
    unpadder  = sym_padding.PKCS7(128).unpadder()
    czysty_zip = unpadder.update(padded) + unpadder.finalize()
    os.makedirs("FA_Paczki_ZIP", exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    with open(os.path.join("FA_Paczki_ZIP", f"paczka_{bazowy_folder}_{ts}.zip"), 'wb') as f:
        f.write(czysty_zip)
    ilosc = 0
    with zipfile.ZipFile(io.BytesIO(czysty_zip)) as z:
        for info in z.infolist():
            if not info.filename.endswith('.xml'):
                continue
            czesci = info.filename.split('-')
            rok_miesiac = f"{czesci[1][:4]}_{czesci[1][4:6]}" if len(czesci) >= 2 and czesci[1].isdigit() else "Pozostale"
            docelowy = os.path.join(bazowy_folder, rok_miesiac)
            os.makedirs(docelowy, exist_ok=True)
            z.extract(info, docelowy)
            ilosc += 1
    print(f"   🎉 Wypakowano {ilosc} plików XML do '{bazowy_folder}'")
    return True

def sledz_status_i_pobierz(access_token, nr_ref, aes_key, iv, bazowy_folder, limit_sekund=1800):
    # Zwraca True tylko gdy paczka faktycznie zostala pobrana i wypakowana.
    # Bez limitu czasu ta petla potrafila wisiec w nieskonczonosc, nic nie logujac.
    print("   🕵️  Oczekuję na wygenerowanie paczki...")
    start = time.time()
    ostatni_kod = ostatni_blad = None
    pobrano = []
    while True:
        if time.time() - start > limit_sekund:
            print(f"   ❌ Przekroczono limit {limit_sekund // 60} min oczekiwania na paczkę "
                  f"(ostatni status: {ostatni_kod}). Przerywam.")
            return False
        try:
            r = requests.get(f"{BASE_URL}/invoices/exports/{nr_ref}",
                             headers={"Authorization": f"Bearer {access_token}"}, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            # chwilowy problem z siecią nie przerywa oczekiwania - pilnuje go limit_sekund
            blad = type(e).__name__
            if blad != ostatni_blad:
                print(f"   ⚠️  Problem z połączeniem przy sprawdzaniu statusu: {blad}. Ponawiam...")
                ostatni_blad = blad
            time.sleep(10)
            continue
        if r.status_code == 200:
            dane = r.json()
            kod = dane.get("status", {}).get("code")
            if kod == 200:
                cnt = dane.get('package', {}).get('invoiceCount', 0)
                print(f"   ✅ Paczka gotowa! Dokumentów: {cnt} (czekano {time.time() - start:.0f}s)")
                for czesc in dane.get('package', {}).get('parts', []):
                    if czesc.get('url'):
                        pobrano.append(pobierz_i_odszyfruj(czesc['url'], aes_key, iv, bazowy_folder))
                if not pobrano:
                    print("   ❌ KSeF zgłosił paczkę gotową, ale nie podał żadnego pliku do pobrania.")
                    return False
                return all(pobrano)
            elif kod == 410:
                print("   ❌ Paczka wygasła lub odrzucona.")
                return False
            else:
                if kod != ostatni_kod:   # loguj tylko zmiany, zamiast zasypywac log co 10 s
                    print(f"   ⏳ Trwa przetwarzanie (status {kod})...")
                    ostatni_kod = kod
                time.sleep(10)
        else:
            blad = f"HTTP {r.status_code}"
            if blad != ostatni_blad:
                print(f"   ⚠️  Nieoczekiwana odpowiedź przy sprawdzaniu statusu: {blad} {r.text[:150]}")
                ostatni_blad = blad
            time.sleep(10)


# ==========================================
# 4. PARSER XML → SŁOWNIKI (POPRAWIONY v7)
# ==========================================
def text_of(node, xpath, default=None):
    if node is None: return default
    el = node.find(xpath)
    return el.text.strip() if el is not None and el.text else default

def float_of(node, xpath, default=None):
    if node is None: return default
    el = node.find(xpath)
    try:    return float(el.text) if el is not None and el.text else default
    except: return default

def date_of(node, xpath, default=None):
    txt = text_of(node, xpath)
    if not txt: return default
    try:    return datetime.fromisoformat(txt[:10]).date()
    except: return default

def datetime_of(node, xpath, default=None):
    """Parsuje pełny datetime (zachowuje godzinę), fallback na samą datę."""
    txt = text_of(node, xpath)
    if not txt: return default
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:    return datetime.strptime(txt[:19], fmt[:len(txt[:19])])
        except: pass
    return default

def bool_of(node, xpath, default=False):
    val = text_of(node, xpath)
    return val in ['1', 'true', 'TAK'] if val else default

def pelny_adres(podmiot_node, tag_adresu='Adres'):
    if podmiot_node is None: return None
    adres_node = podmiot_node.find(f'.//{tag_adresu}')
    if adres_node is None: return None
    l1 = text_of(adres_node, './/AdresL1', '')
    l2 = text_of(adres_node, './/AdresL2', '')
    wynik = f"{l1} {l2}".strip()
    return wynik if wynik else None

def xml_do_dict(element):
    if len(element) == 0: return element.text
    wynik = {}
    for child in element:
        tag = child.tag.split('}', 1)[-1]
        val = xml_do_dict(child)
        if tag in wynik:
            if not isinstance(wynik[tag], list): wynik[tag] = [wynik[tag]]
            wynik[tag].append(val)
        else:
            wynik[tag] = val
    return wynik

def parsuj_podmiot2(root):
    """
    v7 FIX: Pełne parsowanie Podmiot2 (nabywca).
    FA(3) identyfikacja:
      - Polska firma: <NIP>1234567890</NIP>
      - Firma UE:     <NrVatUE>HU10949315</NrVatUE>  pełny
                 LUB  <KodUE>HU</KodUE> + <NrVatUE>10949315</NrVatUE>
      - Spoza UE:     <NrID>...</NrID>
    """
    p2 = root.find('.//Podmiot2')
    if p2 is None:
        return {}

    dane_id = p2.find('.//DaneIdentyfikacyjne')
    nip     = text_of(dane_id, 'NIP')    if dane_id is not None else None
    nr_id   = text_of(dane_id, 'NrID')   if dane_id is not None else None
    nr_vat  = (text_of(dane_id, 'NrVatUE') or '') if dane_id is not None else ''
    kod_ue  = (text_of(dane_id, 'KodUE')  or '') if dane_id is not None else ''

    # Złóż pełny numer VAT UE np. HU10949315
    if kod_ue and nr_vat:
        pelny_vat = nr_vat if nr_vat.upper().startswith(kod_ue.upper()) else (kod_ue + nr_vat)
    elif nr_vat:
        pelny_vat = nr_vat
    elif kod_ue:
        pelny_vat = kod_ue
    else:
        pelny_vat = None

    # Adres nabywcy — strukturalny + kod kraju
    adres_node = p2.find('.//Adres')
    kraj_nab        = text_of(adres_node, 'KodKraju')       if adres_node is not None else None
    kod_pocztowy    = text_of(adres_node, 'KodPocztowy')    if adres_node is not None else None
    miejscowosc     = text_of(adres_node, 'Miejscowosc')    if adres_node is not None else None

    return {
        "nip_nabywcy":          nip,
        "kod_ue_nabywcy":       pelny_vat,
        "nr_id_nabywcy":        nr_id,
        "nazwa_nabywcy":        text_of(p2, './/DaneIdentyfikacyjne//Nazwa'),
        "adres_nabywcy":        pelny_adres(p2, 'Adres'),
        "adres_koresp_nabywcy": pelny_adres(p2, 'AdresKoresp'),
        "nr_klienta":           text_of(p2, './/NrKlienta'),
        "kraj_nabywcy":         kraj_nab,
        "kod_pocztowy_nabywcy": kod_pocztowy,
        "miejscowosc_nabywcy":  miejscowosc,
        "email_nabywcy":        text_of(p2, './/Email'),
        "telefon_nabywcy":      text_of(p2, './/Telefon'),
        "czy_jst":              bool_of(p2, './/JST'),
        "czy_grupa_vat":        bool_of(p2, './/GV'),
    }


def parsuj_do_slownikow(xml_zawartosc, nr_ksef_z_api, nazwa_pliku):
    try:
        surowy_xml_str = xml_zawartosc.decode('utf-8', errors='replace')
        root = ET.fromstring(xml_zawartosc)
        for elem in root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]

        fa = root.find('.//Fa')
        if fa is None:
            return None

        # Hash i URL QR
        hash_sha256 = hashlib.sha256(xml_zawartosc).digest()
        hash_b64    = base64.urlsafe_b64encode(hash_sha256).decode('utf-8').rstrip('=')
        nip_sprz    = text_of(root, './/Podmiot1//NIP', '')
        data_wyst_xml = text_of(fa, 'P_1', '')
        data_wyst_qr = (f"{data_wyst_xml[8:10]}-{data_wyst_xml[5:7]}-{data_wyst_xml[0:4]}"
                        if data_wyst_xml and len(data_wyst_xml) >= 10 else None)
        url_qr = (f"https://qr.ksef.mf.gov.pl/invoice/{nip_sprz}/{data_wyst_qr}/{hash_b64}"
                  if nip_sprz and data_wyst_qr else None)

        plik_dict = {
            "nazwa_pliku": nazwa_pliku,
            "nr_ksef":     nr_ksef_z_api,
            "plik_xml":    surowy_xml_str,
            "xml_hash":    hash_b64,
            "url_qr":      url_qr,
        }

        # Płatności
        kwota_zaplacona = None
        if bool_of(fa, './/Platnosc//Zaplacono'):
            kwota_zaplacona = float_of(fa, 'P_15')
        elif float_of(fa, './/Platnosc//ZaplataCzesciowa//KwotaZaplatyCzesciowej'):
            kwota_zaplacona = float_of(fa, './/Platnosc//ZaplataCzesciowa//KwotaZaplatyCzesciowej')

        konta_lista = [el.text for el in fa.findall('.//Platnosc//RachunekBankowy//NrRB') if el.text]
        konta_lista += [el.text for el in fa.findall('.//Platnosc//RachunekBankowyFaktora//NrRB') if el.text]

        # v7 FIX: Nabywca — pełne dane strukturalne
        nab = parsuj_podmiot2(root)

        # Kurs waluty faktury wg FA(3):
        # - Faktury ZAL: KursWalutyZ na poziomie Fa
        # - Pozostałe EUR/walutowe: KursWaluty na poziomie FaWiersz (per pozycja)
        # Zapamiętujemy jeden kurs na nagłówek (z pierwszej pozycji lub ZAL)
        kurs_wal  = float_of(fa, 'KursWalutyZ')   # dla ZAL
        if not kurs_wal:
            pierwszy_wiersz = root.find('.//FaWiersz')
            kurs_wal = float_of(pierwszy_wiersz, 'KursWaluty') if pierwszy_wiersz is not None else None

        naglowek_dict = {
            "nr_ksef":             nr_ksef_z_api,
            "kod_formularza":      text_of(root, './/Naglowek//KodFormularza'),
            "wariant_formularza":  text_of(root, './/Naglowek//WariantFormularza'),
            "system_info":         text_of(root, './/Naglowek//SystemInfo'),
            # v7 FIX: datetime_of zamiast date_of — zachowujemy pełny timestamp
            "data_wytworzenia_xml": datetime_of(root, './/Naglowek//DataWytworzeniaFa'),
            "miejsce_wystawienia": text_of(fa, 'P_1M'),
            "data_wystawienia":    date_of(fa, 'P_1'),
            "data_sprzedazy":      date_of(fa, 'P_6'),
            "okres_fakturowany_od": date_of(fa, './/OkresFa//P_6_Od'),
            "okres_fakturowany_do": date_of(fa, './/OkresFa//P_6_Do'),
            "nr_faktury_wewn":     text_of(fa, 'P_2'),
            "rodzaj_faktury":      text_of(fa, 'RodzajFaktury'),
            "kod_waluty":          text_of(fa, 'KodWaluty', 'PLN'),
            "znacznik_fp":         bool_of(fa, 'FP'),
            "znacznik_tp":         bool_of(fa, './/TP'),

            "nip_sprzedawcy":      nip_sprz,
            "nazwa_sprzedawcy":    text_of(root, './/Podmiot1//Nazwa'),
            "adres_sprzedawcy":    pelny_adres(root.find('.//Podmiot1'), 'Adres'),
            "adres_koresp_sprzedawcy": pelny_adres(root.find('.//Podmiot1'), 'AdresKoresp'),
            "email_sprzedawcy":    text_of(root, './/Podmiot1//Email'),
            "telefon_sprzedawcy":  text_of(root, './/Podmiot1//Telefon'),
            "kraj_sprzedawcy":     text_of(root, './/Podmiot1//Adres//KodKraju'),

            # v7: pełne dane nabywcy ze struktury parsuj_podmiot2()
            **nab,

            "kurs_waluty":       kurs_wal,
            # Kolumna zarezerwowana: parser nie ma z czego jej wypełnić (brak pola z datą kursu), zostaje NULL
            "data_kursu_waluty": None,

            "kwota_netto_suma":  sum(float(c.text or 0) for c in fa if c.tag.startswith('P_13_') and len(c.tag) <= 8),
            "kwota_vat_suma":    sum(float(c.text or 0) for c in fa if c.tag.startswith('P_14_') and len(c.tag) <= 8),
            "kwota_brutto_suma": float_of(fa, 'P_15'),
            "kwota_do_zaplaty":  float_of(fa, './/Rozliczenie//DoZaplaty'),
            "wartosc_zamowienia": float_of(fa, './/Zamowienie//WartoscZamowienia'),
            "kwota_zaliczki_p15zk": float_of(fa, 'P_15ZK'),

            "netto_23": float_of(fa, 'P_13_1'), "vat_23": float_of(fa, 'P_14_1'), "vat_23_pln": float_of(fa, 'P_14_1W'),
            "netto_8":  float_of(fa, 'P_13_2'), "vat_8":  float_of(fa, 'P_14_2'), "vat_8_pln":  float_of(fa, 'P_14_2W'),
            "netto_5":  float_of(fa, 'P_13_3'), "vat_5":  float_of(fa, 'P_14_3'), "vat_5_pln":  float_of(fa, 'P_14_3W'),
            "netto_0_eksport": float_of(fa, 'P_13_6_3'),
            "netto_0_wdt":     float_of(fa, 'P_13_6_2'),
            "netto_0_inne":    float_of(fa, 'P_13_6_1'),
            "netto_zw":   float_of(fa, 'P_13_7'),
            "netto_oo":   float_of(fa, 'P_13_4'),
            "netto_np":   float_of(fa, 'P_13_5'),
            "netto_wnt":  float_of(fa, 'P_13_9'),
            "netto_marza": float_of(fa, 'P_13_11'),
            "netto_poza_pl":         float_of(fa, 'P_13_8'),   # usługi poza PL (nie OSS)
            "netto_odwr_obciazenie": float_of(fa, 'P_13_10'),  # odwrotne obciążenie krajowe

            "mpp_p18a":             bool_of(fa, './/Adnotacje//P_18A'),
            "metoda_kasowa_p16":    bool_of(fa, './/Adnotacje//P_16'),
            "samofakturowanie_p17": bool_of(fa, './/Adnotacje//P_17'),
            # P_18=1 → odwrotne obciążenie (brak dotychczas w bazie)
            "odwrotne_obciazenie":  bool_of(fa, './/Adnotacje//P_18'),
            # P_23=1 → WNT (bool flag, obok istniejącej kwoty netto_wnt)
            "wnt":                  bool_of(fa, './/Adnotacje//P_23'),
            # P_22=1 → nowe środki transportu
            "nowe_srodki_transportu": bool_of(fa, './/Adnotacje//NoweSrodkiTransportu//P_22'),
            # v7 FIX: P_PMarzy=1 → TAK, P_PMarzyN=1 → NIE (odwrotnie niż w v6!)
            "procedura_marzy":     bool_of(fa, './/Adnotacje//PMarzy//P_PMarzy'),
            "zwolnienie_vat_podstawa": text_of(fa, './/Adnotacje//Zwolnienie//P_19A'),

            "nr_umowy":    text_of(fa, './/WarunkiTransakcji//Umowy//Umowa//NrUmowy'),
            "data_umowy":  date_of(fa, './/WarunkiTransakcji//Umowy//Umowa//DataUmowy'),
            "nr_zamowienia":  text_of(fa, './/WarunkiTransakcji//Zamowienia//NrZamowienia'),
            "data_zamowienia": date_of(fa, './/WarunkiTransakcji//Zamowienia//DataZamowienia'),
            "nr_partii_towaru": text_of(fa, './/WarunkiTransakcji//NrPartiiTowaru'),
            "numery_wz": ", ".join([el.text for el in fa.findall('WZ') if el.text]),
            "warunki_dostawy":  text_of(fa, './/WarunkiTransakcji//WarunkiDostawy'),
            "rodzaj_transportu": text_of(fa, './/Transport//RodzajTransportu'),
            "przewoznik_nip":   text_of(fa, './/Transport//Przewoznik//DaneIdentyfikacyjne//NIP'),
            "przewoznik_nazwa": text_of(fa, './/Transport//Przewoznik//DaneIdentyfikacyjne//Nazwa'),

            "termin_platnosci": ", ".join([el.text for el in fa.findall('.//Platnosc//TerminPlatnosci//Termin') if el.text]),
            "forma_platnosci":  ", ".join([el.text for el in fa.findall('.//Platnosc//FormaPlatnosci') if el.text]),
            "nr_rachunku_bankowego": ", ".join(konta_lista),
            "czy_zaplacono":  bool_of(fa, './/Platnosc//Zaplacono'),
            "data_zaplaty":   date_of(fa, './/Platnosc//DataZaplaty') or date_of(fa, './/Platnosc//ZaplataCzesciowa//DataZaplatyCzesciowej'),
            "kwota_zaplacona": kwota_zaplacona,
            "skonto_kwota":   float_of(fa, './/Platnosc//Skonto//KwotaSkonta'),
            "skonto_warunki": text_of(fa, './/Platnosc//Skonto//WarunkiSkonta'),
            "suma_obciazen":  float_of(fa, './/Rozliczenie//SumaObciazen'),
            "suma_odliczen":  float_of(fa, './/Rozliczenie//SumaOdliczen'),

            "typ_korekty":      text_of(fa, 'TypKorekty'),
            "przyczyna_korekty": text_of(fa, 'PrzyczynaKorekty'),
            "okres_korygowany": text_of(fa, 'OkresFaKorygowanej'),
            "korekta_netto":    float_of(root, './/SumaKorekty//SumaKwotyKorektyNetto'),
            "korekta_vat":      float_of(root, './/SumaKorekty//SumaKwotyKorektyPodatku'),
            "korekta_brutto":   float_of(root, './/SumaKorekty//SumaKwotyKorektyBrutto'),

            "stopka_krs":   text_of(root, './/Stopka//Rejestry//KRS'),
            "stopka_regon": text_of(root, './/Stopka//Rejestry//REGON'),
            "stopka_bdo":   text_of(root, './/Stopka//Rejestry//BDO'),
        }

        # Pozycje faktury
        pozycje_lista = []
        for wiersz in root.findall('.//FaWiersz'):
            rodzaj = naglowek_dict["rodzaj_faktury"] or ""
            pozycje_lista.append({
                "nr_ksef":    nr_ksef_z_api,
                "lp_wiersza": float_of(wiersz, 'NrWierszaFa'),
                "uuid_wiersza": text_of(wiersz, 'UU_ID'),
                "indeks_towaru": text_of(wiersz, 'Indeks'),
                "data_sprzedazy_wiersza": date_of(wiersz, 'P_6A'),
                "nazwa_towaru": text_of(wiersz, 'P_7'),
                "jm":    text_of(wiersz, 'P_8A'),
                "ilosc": float_of(wiersz, 'P_8B'),
                "cena_netto_jedn": float_of(wiersz, 'P_9A'),
                "kwota_rabatu_wiersza":  float_of(wiersz, 'P_10'),
                "wartosc_netto_wiersza": float_of(wiersz, 'P_11'),
                "stawka_vat":    text_of(wiersz, 'P_12'),
                "kwota_vat_wiersza": float_of(wiersz, 'P_11Vat'),
                "cena_brutto_jedn": float_of(wiersz, 'P_9B'),
                "wartosc_brutto_wiersza": float_of(wiersz, 'P_11A'),
                "kurs_waluty":   float_of(wiersz, 'KursWaluty'),
                "kwota_akcyzy":  float_of(wiersz, 'KwotaAkcyzy'),
                "procedura_wiersza": text_of(wiersz, 'Procedura'),
                "stawka_vat_oss":    text_of(wiersz, 'P_12_XII'),  # OSS stawka w kraju nabywcy
                "pkob":              text_of(wiersz, 'PKOB'),
                "stan_pozycji": ("PRZED" if bool_of(wiersz, 'StanPrzed')
                                 else ("PO" if rodzaj in ["KOR", "KOR_ROZ"] else None)),
                "gtu":   text_of(wiersz, 'GTU'),
                "cn":    text_of(wiersz, 'CN'),
                "pkwiu": text_of(wiersz, 'PKWiU'),
            })

        # Zamówienia
        zamowienia_lista = []
        for wiersz in root.findall('.//ZamowienieWiersz'):
            zamowienia_lista.append({
                "nr_ksef":    nr_ksef_z_api,
                "lp_wiersza": float_of(wiersz, 'NrWierszaZam'),
                "uuid_wiersza": text_of(wiersz, 'UU_IDZ'),
                "nazwa_towaru": text_of(wiersz, 'P_7Z'),
                "jm":    text_of(wiersz, 'P_8AZ'),
                "ilosc": float_of(wiersz, 'P_8BZ'),
                "cena_netto_jedn": float_of(wiersz, 'P_9AZ'),
                "kwota_rabatu_wiersza":  float_of(wiersz, 'P_10Z'),
                "wartosc_netto_wiersza": float_of(wiersz, 'P_11NettoZ'),
                "stawka_vat":        text_of(wiersz, 'P_12Z'),
                "kwota_vat_wiersza": float_of(wiersz, 'P_11VatZ'),
                "stan_pozycji": ("PRZED" if bool_of(wiersz, 'StanPrzedZ')
                                 else ("PO" if naglowek_dict["rodzaj_faktury"] == "KOR_ZAL" else None)),
            })

        # Podmioty trzecie
        podmioty_lista = []
        for tag_nazwa in ['Podmiot3', 'PodmiotUpowazniony']:
            for p in root.findall(f'.//{tag_nazwa}'):
                podmioty_lista.append({
                    "nr_ksef":     nr_ksef_z_api,
                    "typ_podmiotu": tag_nazwa,
                    "rola":   text_of(p, 'Rola'),
                    "nip":    text_of(p, './/NIP'),
                    "nazwa":  text_of(p, './/Nazwa'),
                    "adres":  pelny_adres(p),
                    "email":  text_of(p, './/Email'),
                    "telefon": text_of(p, './/Telefon'),
                    "udzial": float_of(p, 'Udzial'),
                })

        # Faktury korygowane
        korekty_lista = [
            {
                "nr_ksef_korekty":      nr_ksef_z_api,
                "nr_korygowanej_wewn":  text_of(kor, 'NrFaKorygowanej'),
                "nr_korygowanej_ksef":  text_of(kor, 'NrKSeFFaKorygowanej'),
                "data_wyst_korygowanej": date_of(kor, 'DataWystFaKorygowanej'),
                "czy_ksef": bool_of(kor, 'NrKSeF'),  # NrKSeF=1 → była w KSeF
            }
            for kor in root.findall('.//DaneFaKorygowanej')
        ]

        # Faktury zaliczkowe
        zaliczki_lista = [
            {
                "nr_ksef_rozliczeniowej": nr_ksef_z_api,
                "nr_ksef_zaliczkowej":    text_of(zal, 'NrKSeFFaZaliczkowej'),
            }
            for zal in root.findall('.//FakturaZaliczkowa')
        ]

        # Dodatkowe opisy
        opisy_lista = [
            {"nr_ksef": nr_ksef_z_api, "klucz": text_of(op, 'Klucz'), "wartosc": text_of(op, 'Wartosc')}
            for op in root.findall('.//DodatkowyOpis')
        ]

        # Załączniki
        zalaczniki_lista = []
        zal_xml = root.find('.//Zalacznik')
        if zal_xml is not None:
            zalaczniki_lista.append({"nr_ksef": nr_ksef_z_api, "zawartosc_json": xml_do_dict(zal_xml)})

        return {
            "plik": plik_dict, "naglowek": naglowek_dict, "pozycje": pozycje_lista,
            "zamowienia": zamowienia_lista, "podmioty": podmioty_lista,
            "korekty": korekty_lista, "zaliczki": zaliczki_lista,
            "opisy": opisy_lista, "zalaczniki": zalaczniki_lista,
        }

    except Exception as e:
        print(f"   ⚠️  Błąd parsowania {nazwa_pliku}: {e}")
        return None


# ==========================================
# 5. ZAPIS DO POSTGRESQL
# ==========================================
ROZMIAR_WSADU = 500  # ile dokumentów zapisujemy naraz

def zaladuj_do_postgresql():
    print("\n" + "=" * 55)
    print("🚀 FAZA 2: IMPORT DANYCH DO BAZY POSTGRESQL")
    print("=" * 55)
    session = SessionLocal()

    istniejace_ksefy = {row[0] for row in session.query(KsefPlikXml.nr_ksef).all()}
    print(f"🔍 W bazie: {len(istniejace_ksefy)} faktur (pomijam duplikaty).")

    folder_typ = {"FA_Sprzedaz": "S", "FA_Zakupy": "Z"}
    for folder in ["FA_Sprzedaz", "FA_Zakupy"]:
        if not os.path.exists(folder):
            continue

        pliki_xml = [
            os.path.join(r, f)
            for r, _, fs in os.walk(folder)
            for f in fs if f.endswith(".xml")
        ]
        nowe_pliki = [p for p in pliki_xml if os.path.basename(p).replace(".xml", "") not in istniejace_ksefy]

        if not nowe_pliki:
            print(f"📭 Brak nowych plików w '{folder}'.")
            continue

        print(f"\n📂 Folder '{folder}': {len(nowe_pliki)} nowych plików do wczytania...")
        bledy = 0

        # Przetwarzamy w wsadach
        for start in range(0, len(nowe_pliki), ROZMIAR_WSADU):
            wsad_pliki = nowe_pliki[start:start + ROZMIAR_WSADU]
            zbior = {k: [] for k in ["plik", "naglowek", "pozycje", "zamowienia", "podmioty", "korekty", "zaliczki", "opisy", "zalaczniki"]}

            for sciezka in wsad_pliki:
                nr_ksef = os.path.basename(sciezka).replace(".xml", "")
                try:
                    with open(sciezka, "rb") as f:
                        wynik = parsuj_do_slownikow(f.read(), nr_ksef, os.path.basename(sciezka))
                    if wynik:
                        # Ustaw typ_podmiotu (S=sprzedaż, Z=zakup) na podstawie folderu
                        wynik["naglowek"]["typ_podmiotu"] = folder_typ.get(folder, "S")
                        wynik["plik"]["typ_podmiotu"]     = folder_typ.get(folder, "S")
                        for klucz in zbior:
                            if isinstance(wynik[klucz], list): zbior[klucz].extend(wynik[klucz])
                            elif wynik[klucz]:                 zbior[klucz].append(wynik[klucz])
                    else:
                        bledy += 1
                except Exception as e:
                    print(f"   ⚠️  Błąd odczytu {nr_ksef}: {e}")
                    bledy += 1

            if not zbior["plik"]:
                continue

            print(f"   ⏳ Zapisuję wsad {start+1}–{min(start+ROZMIAR_WSADU, len(nowe_pliki))} ({len(zbior['plik'])} dok.)...")
            try:
                session.bulk_insert_mappings(KsefPlikXml,    zbior["plik"])
                session.bulk_insert_mappings(KsefNaglowek,   zbior["naglowek"])
                if zbior["pozycje"]:    session.bulk_insert_mappings(KsefPozycja,           zbior["pozycje"])
                if zbior["zamowienia"]: session.bulk_insert_mappings(KsefZamowienieWiersz,  zbior["zamowienia"])
                if zbior["podmioty"]:   session.bulk_insert_mappings(KsefPodmiotTrzeci,     zbior["podmioty"])
                if zbior["korekty"]:    session.bulk_insert_mappings(KsefFakturaKorygowana, zbior["korekty"])
                if zbior["zaliczki"]:   session.bulk_insert_mappings(KsefFakturaZaliczkowa, zbior["zaliczki"])
                if zbior["opisy"]:      session.bulk_insert_mappings(KsefDodatkowyOpis,     zbior["opisy"])
                if zbior["zalaczniki"]: session.bulk_insert_mappings(KsefZalacznik,         zbior["zalaczniki"])
                session.commit()
                istniejace_ksefy.update(p['nr_ksef'] for p in zbior["plik"])
            except Exception as e:
                session.rollback()
                print(f"   ❌ Błąd zapisu wsadu: {e}")

        print(f"✅ Folder '{folder}' zakończony. Błędy parsowania: {bledy}")

    session.close()


# ==========================================
# 6. GŁÓWNY PROCES
# ==========================================
def main_combo():
    sys.stdout.reconfigure(line_buffering=True)   # zeby log rosl na biezaco, a nie dopiero na koncu
    start = datetime.now()
    print("=" * 55)
    print(f"🌟 ROBOT KSeF v7 🌟   start: {start:%Y-%m-%d %H:%M:%S}")
    print(f"📅 Okres: {DATA_OD_DT:%Y-%m-%d} → {DATA_DO_DT:%Y-%m-%d}")
    print("=" * 55)

    problemy = []
    try:
        print("\n🚀 FAZA 1: ŁĄCZENIE Z KSeF API")
        challenge, timestamp_ms = pobierz_wyzwanie()
        klucz_auth, klucz_aes   = pobierz_klucze_rsa()
        nr_ref, auth_token       = autoryzuj_sie(NIP_FIRMY, challenge, timestamp_ms, klucz_auth)
        access_token             = pobierz_token_jwt(nr_ref, auth_token)
        print("   ✅ Sesja uwierzytelniona!")

        q_id_s, aes_s, iv_s = inicjuj_eksport_zip(access_token, "subject1", "SPRZEDAŻ", klucz_aes)
        if not q_id_s:
            problemy.append("SPRZEDAŻ: nie udało się zlecić eksportu")
        elif not sledz_status_i_pobierz(access_token, q_id_s, aes_s, iv_s, "FA_Sprzedaz"):
            problemy.append("SPRZEDAŻ: paczka nie została pobrana")

        q_id_z, aes_z, iv_z = inicjuj_eksport_zip(access_token, "subject2", "ZAKUP", klucz_aes)
        if not q_id_z:
            problemy.append("ZAKUP: nie udało się zlecić eksportu")
        elif not sledz_status_i_pobierz(access_token, q_id_z, aes_z, iv_z, "FA_Zakupy"):
            problemy.append("ZAKUP: paczka nie została pobrana")

        zaladuj_do_postgresql()
    except Exception as e:
        problemy.append(f"błąd krytyczny: {e}")
        print(f"\n❌ Błąd krytyczny: {e}")
        traceback.print_exc()

    koniec = datetime.now()
    trwalo = (koniec - start).total_seconds()
    print()
    print("=" * 55)
    if problemy:
        print(f"❌ PROCES ZAKOŃCZONY Z BŁĘDAMI — koniec: {koniec:%Y-%m-%d %H:%M:%S} (trwał {trwalo:.0f}s)")
        for p in problemy:
            print(f"   • {p}")
    else:
        print(f"🏁 PROCES ZAKOŃCZONY SUKCESEM! — koniec: {koniec:%Y-%m-%d %H:%M:%S} (trwał {trwalo:.0f}s)")
    print("=" * 55)
    return 1 if problemy else 0


if __name__ == "__main__":
    sys.exit(main_combo())
