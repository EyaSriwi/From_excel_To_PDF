import os
import tempfile
from datetime import datetime
import pandas as pd
import unicodedata
from tkinter import Tk, Frame, Label, Button, Entry, StringVar, OptionMenu, LEFT, RIGHT, BOTH, X
from tkinter import messagebox, Listbox, Scrollbar, Toplevel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from PIL import Image, ImageTk
import fitz  # PyMuPDF
import io

# ----------------- Configuration -----------------
EMPLOYEES_FILE = 'lll.CSV'
LOGO_PATH = 'logo.jpg'
LOGO = 'logo.png'
STAMP_PATH = 'cachet.png'
OUTPUT_PDF = 'lettre_liaison.pdf'
BASE_FILE = 'Base_LettreLiaison.xlsx'
BASE_COLUMNS = ['Matricule', 'Nom & Prénom', 'CIN', 'CNSS', 'Date d\'admission', 'Lieu d\'admission', 'Type de prise en charge']

HOSPITAUX = {
    'Hôpital Korba': 'Rue Abou Kacem CHEBBI, 8070 KORBA NABEUL',
    'Groupement Médecine du Travail': 'Av. Hédi Nouira, 8000 Nabeul',
    'Polyclinique El Hakim': 'Km 1 Route Korba Tazarka, 8024 Korba, Nabeul Gouvernorat',
    'Polyclinique El Amen': 'Av. Hédi Nouira, Nabeul'
}

ENTREPRISE_INFO = {
    'name': 'CF MAIER ITAP',
    'address': 'Z.I El Mazraa, 8024 Tazarka, Tunisie',
    'phone': '+216 72 225 278 / +216 72 225 279',
    'fax': '+216 72 225 435'
}

# ----------------- Helpers -----------------
def remove_accents(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join([c for c in nfkd if not unicodedata.combining(c)])

def deduplicate_columns(columns):
    """Ajoute .1, .2, etc. aux colonnes dupliquées pour les rendre uniques."""
    seen = {}
    new_cols = []
    for col in columns:
        if col not in seen:
            seen[col] = 0
            new_cols.append(col)
        else:
            seen[col] += 1
            new_cols.append(f"{col}.{seen[col]}")
    return new_cols

def format_cin(cin):
    """Formate le CIN sur 8 chiffres, en ajoutant des zéros au début si nécessaire"""
    if pd.isna(cin) or str(cin).strip() == '':
        return ''
    s = ''.join(ch for ch in str(cin) if ch.isdigit())
    return s.zfill(8)

def format_num(num):
    """Formate la clé Num sur 2 chiffres"""
    if pd.isna(num) or str(num).strip() == '':
        return ''
    s = ''.join(ch for ch in str(num) if ch.isdigit())
    return s.zfill(2)

def clean_csv_value(val):
    """
    Supprime ="" autour des valeurs et espace inutile.
    Exemple : '="230065"' -> '230065'
    """
    if pd.isna(val):
        return ''
    val = str(val).strip()
    if val.startswith('="') and val.endswith('"'):
        val = val[2:-1]  # supprime ="
    return val.strip()

def normalize_employee_columns(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[DEBUG] Colonnes brutes depuis le fichier :", list(df.columns))
    df.columns = deduplicate_columns(df.columns)
    print("[DEBUG] Colonnes après déduplication :", list(df.columns))

    mapping = {}
    for col in df.columns:
        key = remove_accents(col).strip().lower()
        if 'matric' in key:
            mapping[col] = 'Matricule'
        elif 'prenom' in key or 'prénom' in key:
            mapping[col] = 'Prénom'
        elif 'nom' in key:
            mapping[col] = 'Nom'
        elif 'carte de sejour' in key or 'carte de travail' in key:
            mapping[col] = 'CIN'
        elif 'numéro de securite' in key or 'numero de securite' in key:
            mapping[col] = 'CNSS'
        elif 'clé du numéro de securite' in key or 'cle du numero de securite' in key:
            mapping[col] = 'Num'


    print("[DEBUG] Mapping appliqué :", mapping)

    df = df.rename(columns=mapping)
    # Supprimer les colonnes dupliquées restantes
    df = df.loc[:, ~df.columns.duplicated()]
    print("[DEBUG] Colonnes après renommage et déduplication :", list(df.columns))

    # Ajouter les colonnes manquantes
    for needed in ['Matricule', 'Nom', 'Prénom', 'CIN', 'CNSS', 'Num']:
        if needed not in df.columns:
            df[needed] = ''

    # Nettoyer les espaces
    for col in ['Matricule', 'Nom', 'Prénom', 'CIN', 'CNSS', 'Num']:
        df[col] = df[col].astype(str).str.strip()

    return df

def update_cnss_with_num(df):
    """Concatène CNSS et Num pour obtenir le numéro complet"""
    if 'CNSS' not in df.columns:
        df['CNSS'] = ''
    if 'Num' not in df.columns:
        df['Num'] = ''

    df['Num'] = df['Num'].apply(format_num)
    df['CNSS'] = df['CNSS'].astype(str).str.strip() + df['Num']
    df['CNSS'] = df['CNSS'].apply(lambda x: x if len(x) >= 8 else '')

    return df

# ----------------- Main Loader -----------------
def load_employees():
    if not os.path.exists(EMPLOYEES_FILE):
        raise FileNotFoundError(f"Fichier employés introuvable: {EMPLOYEES_FILE}")
    
    df = pd.read_csv(EMPLOYEES_FILE, sep=';', encoding='cp1252')
    print("[DEBUG] Shape du fichier chargé :", df.shape)

    # Nettoyer toutes les cellules du CSV
    df = df.applymap(clean_csv_value)

    # Normaliser les colonnes
    df = normalize_employee_columns(df)
    print("[DEBUG] Shape après normalisation :", df.shape)

    # Formater CIN
    df['CIN'] = df['CIN'].apply(format_cin)

    # Concaténer CNSS + Num
    df = update_cnss_with_num(df)
    print("[DEBUG] Quelques lignes après update CNSS :\n", df.head())

    return df

# ----------------- PDF Generation -----------------
def generate_pdf(data, hospital_name, hospital_address):
    c = canvas.Canvas(OUTPUT_PDF, pagesize=A4)
    width, height = A4
    margin = 20 * mm
    top_margin = 68 * mm
    logo_width = 40 * mm

    # Logo top-right
    if os.path.exists(LOGO_PATH):
        x = width - margin - logo_width
        y = height - top_margin - logo_width
        c.drawImage(LOGO_PATH, x, y, width=logo_width, preserveAspectRatio=True)

    # Company info left
    c.setFont('Helvetica-Bold', 10)
    c.drawString(margin, height - 40*mm, f"Nom de l'entreprise : {ENTREPRISE_INFO['name']}")
    c.setFont('Helvetica', 10)
    c.drawString(margin, height - 45*mm, f"Adresse : {ENTREPRISE_INFO['address']}")
    c.drawString(margin, height - 50*mm, f"Télephone : {ENTREPRISE_INFO['phone']}")
    c.drawString(margin, height - 55*mm, f"Fax : {ENTREPRISE_INFO['fax']}")

    # Titles centered
    c.setFont('Helvetica-Bold', 16)
    c.drawCentredString(width/2, height - 70*mm, "LETTRE DE LIAISON")
    c.setFont('Helvetica-Bold', 12)
    c.drawCentredString(width/2, height - 80*mm, "ADMISSION D’UN PATIENT")

    today = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    c.setFont('Helvetica', 10)
    c.drawString(margin, height - 95*mm, f"Date : {today}")

    # Corps du texte
    y = height - 105*mm
    lines = [
        f"La société {ENTREPRISE_INFO['name']} demande au {hospital_name} l’admission d’un patient affilié {ENTREPRISE_INFO['name']} :",
        f"Lieu d'admission : {hospital_name}",
        f"Adresse : {hospital_address}",
        f"Matricule : {data.get('Matricule','')}",
        f"Nom du patient : {data.get('Nom','')} {data.get('Prénom','')}",
        "Nationalité : Tunisienne",
        f"Numéro CIN : {data.get('CIN','')}",
        f"CNSS : {data.get('CNSS','')}",
        f"Médecin requérant : {data.get('MedecinRequerant','')}",
        f"Médecin(s) traitant(s) : {data.get('MedecinTraitant','')}",
        f"Date d'admission : {data.get('DateAdmission','')}",
        f"Type de prise en charge : {data.get('TypePriseEnCharge','')}"
    ]

    c.setFont('Helvetica', 10)
    for line in lines:
        wrapped = simpleSplit(line, 'Helvetica', 10, width - 2*margin)
        for wline in wrapped:
            c.drawString(margin, y, wline)
            y -= 6.5*mm

    # Retour à la ligne avant le paragraphe principal
    y -= 6.5*mm

    # Paragraphe principal
    paragraph = f"Prise en charge Totale par {ENTREPRISE_INFO['name']} : La facture du {hospital_name} est à régler totalement par {ENTREPRISE_INFO['name']}."
    wrapped = simpleSplit(paragraph, 'Helvetica', 10, width - 2*margin)
    for wline in wrapped:
        c.drawString(margin, y, wline)
        y -= 6.5*mm
    y -= 20*mm
    # Deux petites lignes avant le cachet
    c.setFont('Helvetica-Bold', 10)
    c.drawString(margin, y, "Signature et cachet")
    y -= 10*mm
    c.drawString(margin, y, "CF MAIER ITAP")
    y -= 10*mm

    # Cachet
    if os.path.exists(STAMP_PATH):
        c.drawImage(STAMP_PATH, margin, 20*mm, width=40*mm, preserveAspectRatio=True)

    # Nom de l'hôpital à droite
    c.setFont('Helvetica-Bold', 10)
    c.drawRightString(width - margin, 50*mm, hospital_name)
    
    c.save()
# ----------------- Enregistrement dans la base -----------------
    try:
        if os.path.exists(BASE_FILE):
            base_df = pd.read_excel(BASE_FILE, engine='openpyxl')
        else:
            base_df = pd.DataFrame(columns=BASE_COLUMNS + ['Hôpital', "Date d'enregistrement"])
        
        data_to_save = {
            'Matricule': data.get('Matricule',''),
            'Nom & Prénom': f"{data.get('Nom','')} {data.get('Prénom','')}".strip(),
            'CIN': data.get('CIN',''),
            'CNSS': data.get('CNSS',''),
            'Date d\'admission': data.get('DateAdmission',''),
            'Type de prise en charge': data.get('TypePriseEnCharge',''),
            'Hôpital': hospital_name,
            "Date d'enregistrement": datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        }

        # Évite les doublons
        if not ((base_df['Matricule'] == data_to_save['Matricule']) &
                (base_df['Date d\'admission'] == data_to_save['Date d\'admission'])).any():
            base_df = pd.concat([base_df, pd.DataFrame([data_to_save])], ignore_index=True)
            base_df.to_excel(BASE_FILE, index=False, engine='openpyxl')
        else:
            print("Formulaire déjà enregistré dans la base.")
    except Exception as e:
        print(f"Erreur lors de l'enregistrement dans la base: {e}")
# ----------------- Tkinter App -----------------

class App:
    def __init__(self, master):
        self.master = master
        try:
            self.df = load_employees()
        except Exception as e:
            messagebox.showerror('Erreur', str(e))
            self.df = pd.DataFrame(columns=['Matricule','Nom','Prénom','CIN','CNSS'])

        # --- Helper to remove accents ---
        def remove_accents(input_str):
            return ''.join(
                c for c in unicodedata.normalize('NFD', input_str)
                if unicodedata.category(c) != 'Mn'
            )
        self.remove_accents = remove_accents

        # --- Variables ---
        self.hopital_var = StringVar(value=list(HOSPITAUX.keys())[0]) 
        self.matricule_var = StringVar()
        self.nom_prenom_var = StringVar()
        self.cin_var = StringVar()
        self.cnss_var = StringVar()
        self.medecin_r_var = StringVar()
        self.medecin_t_var = StringVar()
        self.date_var = StringVar(value=datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
        self.type_var = StringVar(value='Consultation médicale')

        for var in [self.hopital_var, self.matricule_var, self.nom_prenom_var,
                    self.cin_var, self.cnss_var, self.medecin_r_var, self.medecin_t_var,
                    self.date_var, self.type_var]:
            var.trace_add('write', lambda *args: self.update_preview())

        # --- UI Layout ---
        left = Frame(master)
        left.pack(side=LEFT, fill=BOTH, expand=True, padx=10, pady=10)
        right = Frame(master)
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=10, pady=10)

        if os.path.exists(LOGO):
            img = Image.open(LOGO)
            img.thumbnail((150,150))
            self.logo_img = ImageTk.PhotoImage(img)
            Label(left, image=self.logo_img).pack(anchor='ne')

        Label(left, text="Lieu d'admission :").pack()
        OptionMenu(left, self.hopital_var, *HOSPITAUX.keys()).pack(fill=X)

        # Matricule search with autocomplete
        Label(left, text="Matricule").pack(anchor='w', pady=(6,0))
        frame_matricule = Frame(left)
        frame_matricule.pack(fill=X)
        self.matricule_entry = Entry(frame_matricule, textvariable=self.matricule_var, font=('Helvetica', 14))
        self.matricule_entry.pack(side=LEFT, fill=X, expand=True, ipady=5)
        self.matricule_entry.bind('<KeyRelease>', self.on_matricule_typing)
        Button(frame_matricule, text="🔍", command=self.search_by_matricule,
            font=('Helvetica', 14), padx=10).pack(side=RIGHT, ipady=2)
        self.listbox_window_matricule = None

        # Name search with autocomplete
        Label(left, text="Nom & Prénom").pack(anchor='w', pady=(6,0))
        frame_nom = Frame(left)
        frame_nom.pack(fill=X)
        self.nom_entry = Entry(frame_nom, textvariable=self.nom_prenom_var, font=('Helvetica', 14))
        self.nom_entry.pack(side=LEFT, fill=X, expand=True, ipady=5)
        self.nom_entry.bind('<KeyRelease>', self.on_name_typing)
        Button(frame_nom, text="🔍", command=self.search_by_name,
            font=('Helvetica', 14), padx=10).pack(side=RIGHT, ipady=2)
        self.listbox_window_name = None

        # Other fields
        for label, var in [
            ("CIN", self.cin_var),
            ("CNSS", self.cnss_var),
            ("Médecin requérant", self.medecin_r_var),
            ("Médecin(s) traitant(s)", self.medecin_t_var),
            ("Date admission (jj/mm/aaaa HH:MM:SS)", self.date_var),
            ("Type de prise en charge", self.type_var)
        ]:
            Label(left, text=label).pack(anchor='w', pady=(6,0))
            Entry(left, textvariable=var, font=('Helvetica', 14)).pack(fill=X, ipady=5)

        # Buttons side-by-side
        buttons_frame = Frame(left)
        buttons_frame.pack(pady=6, fill=X)
        Button(buttons_frame, text="Générer PDF", command=self.generate, font=('Helvetica', 12), padx=10, pady=5).pack(
            side=LEFT, expand=True, fill=X, padx=5
        )
        Button(buttons_frame, text="Effacer Formulaire", command=self.clear_form, font=('Helvetica', 12), padx=10, pady=5).pack(
            side=LEFT, expand=True, fill=X, padx=5
        )

        # Preview
        Label(right, text='Aperçu PDF:').pack()
        self.preview_label = Label(right)
        self.preview_label.pack()

    # ----------------- Search Methods -----------------
    def search_by_matricule(self):
        m = self.matricule_var.get().strip()
        if not m:
            messagebox.showinfo('Info', 'Entrez un matricule à rechercher.')
            return
        row = self.df[self.df['Matricule'].astype(str).str.contains(m, case=False, na=False)]
        if row.empty:
            messagebox.showinfo('Résultat', 'Aucun employé trouvé.')
            return
        self.fill_fields(row.iloc[0])

    def search_by_name(self):
        input_str = self.nom_prenom_var.get().strip()
        if not input_str:
            messagebox.showinfo('Info', 'Entrez Nom et/ou Prénom.')
            return
        input_norm = self.remove_accents(input_str.lower())
        self.df['NomComplet'] = self.df.apply(
            lambda row: self.remove_accents(f"{row['Nom']} {row['Prénom']}".lower().strip()),
            axis=1
        )
        mask = self.df['NomComplet'].str.contains(input_norm, na=False)
        row = self.df[mask]
        if row.empty:
            messagebox.showinfo('Résultat', 'Aucun employé trouvé.')
            return
        self.fill_fields(row.iloc[0])

    def fill_fields(self, row):
        self.matricule_var.set(str(row.get('Matricule','')).strip())
        self.nom_prenom_var.set(f"{row.get('Nom','').strip()} {row.get('Prénom','').strip()}")
        self.cin_var.set(format_cin(row.get('CIN','')))
        self.cnss_var.set(str(row.get('CNSS','')).strip())
        self.update_preview()

    # ----------------- Autocomplete Methods -----------------
    def on_name_typing(self, event):
        text = self.nom_prenom_var.get().strip().lower()
        if not text:
            if self.listbox_window_name:
                self.listbox_window_name.destroy()
            return

        self.df['NomComplet'] = self.df.apply(
            lambda row: self.remove_accents(f"{row['Nom']} {row['Prénom']}".lower().strip()),
            axis=1
        )
        input_norm = self.remove_accents(text)
        matches = self.df[self.df['NomComplet'].str.contains(input_norm, na=False)]['NomComplet'].tolist()

        if matches:
            if self.listbox_window_name:
                self.listbox_window_name.destroy()
            self.listbox_window_name = Toplevel(self.master)
            self.listbox_window_name.overrideredirect(True)
            x = self.nom_entry.winfo_rootx()
            y = self.nom_entry.winfo_rooty() + self.nom_entry.winfo_height()
            self.listbox_window_name.geometry(f"+{x}+{y}")

            listbox = Listbox(self.listbox_window_name, width=40)
            listbox.pack()
            for match in matches:
                listbox.insert('end', match)

            listbox.bind("<<ListboxSelect>>", lambda e: self.select_autocomplete_name(listbox))
        else:
            if self.listbox_window_name:
                self.listbox_window_name.destroy()

    def select_autocomplete_name(self, listbox):
        selection = listbox.get(listbox.curselection())
        self.nom_prenom_var.set(selection)
        if self.listbox_window_name:
            self.listbox_window_name.destroy()
        row = self.df[self.df['NomComplet'] == self.remove_accents(selection.lower())]
        if not row.empty:
            self.fill_fields(row.iloc[0])

    def on_matricule_typing(self, event):
        text = self.matricule_var.get().strip().lower()
        if not text:
            if self.listbox_window_matricule:
                self.listbox_window_matricule.destroy()
            return
        matches = self.df[self.df['Matricule'].astype(str).str.lower().str.contains(text, na=False)]['Matricule'].tolist()

        if matches:
            if self.listbox_window_matricule:
                self.listbox_window_matricule.destroy()
            self.listbox_window_matricule = Toplevel(self.master)
            self.listbox_window_matricule.overrideredirect(True)
            x = self.matricule_entry.winfo_rootx()
            y = self.matricule_entry.winfo_rooty() + self.matricule_entry.winfo_height()
            self.listbox_window_matricule.geometry(f"+{x}+{y}")

            listbox = Listbox(self.listbox_window_matricule, width=20)
            listbox.pack()
            for match in matches:
                listbox.insert('end', match)

            listbox.bind("<<ListboxSelect>>", lambda e: self.select_autocomplete_matricule(listbox))
        else:
            if self.listbox_window_matricule:
                self.listbox_window_matricule.destroy()

    def select_autocomplete_matricule(self, listbox):
        selection = listbox.get(listbox.curselection())
        self.matricule_var.set(selection)
        if self.listbox_window_matricule:
            self.listbox_window_matricule.destroy()
        row = self.df[self.df['Matricule'].astype(str) == selection]
        if not row.empty:
            self.fill_fields(row.iloc[0])


    # --------- Génération PDF ---------
    def generate(self):
        data = {
            'Matricule': self.matricule_var.get().strip(),
            'Nom': self.nom_prenom_var.get().strip().split()[0] if self.nom_prenom_var.get().strip() else '',
            'Prénom': self.nom_prenom_var.get().strip().split()[1] if len(self.nom_prenom_var.get().strip().split())>1 else '',
            'CIN': format_cin(self.cin_var.get()),
            'CNSS': self.cnss_var.get().strip(),
            'MedecinRequerant': self.medecin_r_var.get().strip(),
            'MedecinTraitant': self.medecin_t_var.get().strip(),
            'DateAdmission': self.date_var.get().strip(),
            'TypePriseEnCharge': self.type_var.get().strip()
        }
        hopital = self.hopital_var.get()
        adresse = HOSPITAUX[hopital]
        generate_pdf(data, hopital, adresse)
        messagebox.showinfo('Succès', f'PDF généré: {OUTPUT_PDF}')
        self.update_preview()

    # --------- Effacer formulaire ---------
    def clear_form(self):
        for var in [self.matricule_var, self.nom_prenom_var, self.cin_var, self.cnss_var,
                    self.medecin_r_var, self.medecin_t_var, self.date_var, self.type_var]:
            var.set('')
        self.hopital_var.set(list(HOSPITAUX.keys())[0])
        self.update_preview()

    def update_preview(self):
        try:
            # Récupération des données
            matricule = self.matricule_var.get().strip()
            nom_prenom = self.nom_prenom_var.get().strip().split()
            nom = nom_prenom[0] if nom_prenom else ''
            prenom = nom_prenom[1] if len(nom_prenom) > 1 else ''
            data = {
                'Matricule': matricule,
                'Nom': nom,
                'Prénom': prenom,
                'CIN': format_cin(self.cin_var.get()),
                'CNSS': self.cnss_var.get().strip(),
                'Médecin Requérant': self.medecin_r_var.get().strip(),
                'Médecin Traitant': self.medecin_t_var.get().strip(),
                'Date d\'admission': self.date_var.get().strip(),
                'Type de prise en charge': self.type_var.get().strip()
            }

            hopital = self.hopital_var.get()
            adresse = HOSPITAUX[hopital]

            # Création du PDF en mémoire
            doc = fitz.open()
            page = doc.new_page()
            
            text = f"""
==================== LETTRE DE LIAISON ====================

 Date : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

 Hôpital : {hopital}
 Adresse : {adresse}

 Informations Patient
  - Matricule       : {data['Matricule']}
  - Nom             : {data['Nom']}
  - Prénom          : {data['Prénom']}
  - CIN             : {data['CIN']}
  - CNSS            : {data['CNSS']}

 Médecins
  - Requérant       : {data['Médecin Requérant']}
  - Traitant        : {data['Médecin Traitant']}

 Date d'admission   : {data['Date d\'admission']}
 Type prise en charge: {data['Type de prise en charge']}

------------------------------------------------------------
Prise en charge Totale par {ENTREPRISE_INFO['name']} :
La facture du {hopital} est à régler totalement par {ENTREPRISE_INFO['name']}.
============================================================
"""
            # Insérer le texte dans une zone avec marges
            rect = fitz.Rect(50, 50, 550, 750)
            page.insert_textbox(rect, text, fontsize=12, fontname="helv", align=0)  # align=0 => left

            # Convertir en image pour Tkinter
            pix = page.get_pixmap()
            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))
            img.thumbnail((450, 600))
            self.preview_image = ImageTk.PhotoImage(img)
            self.preview_label.config(image=self.preview_image, text='')
        except Exception as e:
            self.preview_label.config(text=f"Aperçu indisponible: {e}", image='')

# --------- Lancement ---------
if __name__ == '__main__':
    root = Tk()
    root.geometry('1000x700')
    root.title('Générateur Lettre de Liaison - CF MAIER ITAP')
    app = App(root)
    root.mainloop()
