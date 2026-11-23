# ==========================================================
#  Script de demarrage : Explorateur avec onglets + Outlook + autre appli
# ==========================================================
#
#  INSTALLATION (a faire une seule fois, a la main)
#  ------------------------------------------------
#  But : lancer ce script automatiquement a chaque ouverture de session.
#
#  1. Personnalise la section 1 ci-dessous (dossiers, autre appli).
#
#  2. Enregistre ce fichier a un emplacement fixe, par exemple :
#        C:\Scripts\demarrage.ps1
#     (si tu le deplaces plus tard, il faudra refaire l'etape 4)
#
#  3. Ouvre le dossier Demarrage de Windows :
#        Win + R  ->  tape  shell:startup  ->  Entree
#
#  4. Dans ce dossier : clic droit > Nouveau > Raccourci.
#     Dans "Entrez l'emplacement de l'element", colle :
#
#        powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\Scripts\demarrage.ps1"
#
#     (adapte le chemin si tu as enregistre le script ailleurs)
#     Clique sur Suivant, donne un nom (ex. "Mon demarrage"), puis Terminer.
#
#  5. Test : double-clique sur le raccourci cree. Le script doit
#     s'executer (attente de 15 s, puis ouverture des applis).
#
#  Le script se lancera desormais a chaque ouverture de session.
#
#  DESINSTALLATION
#  ---------------
#  Win + R  ->  shell:startup  ->  supprime le raccourci "Mon demarrage".
#
#  REMARQUES
#  ---------
#  - Pendant l'ouverture des onglets, ne touche ni la souris ni le
#    clavier (le script simule des touches : Ctrl+T, Ctrl+L...).
#  - Si tes chemins contiennent des accents, enregistre ce fichier
#    dans le Bloc-notes en "UTF-8 avec BOM".
# ==========================================================

# --- 1. A PERSONNALISER --------------------------------------------------

# Dossiers a ouvrir dans l'Explorateur (le premier = premier onglet)
$dossiers = @(
    "$env:USERPROFILE\Documents",
    "$env:USERPROFILE\Downloads",
    "$env:USERPROFILE\Desktop",
    "C:\Projets"                      # <- remplace par tes propres chemins
)

# Autre application a lancer (chemin complet vers le .exe)
$autreAppli = "C:\Program Files\Notepad++\notepad++.exe"   # <- a modifier

# Attente au demarrage (secondes) pour laisser Windows finir de charger
$delaiInitial = 15

# --- 2. PREPARATION ------------------------------------------------------

Start-Sleep -Seconds $delaiInitial

Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Fenetre {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

# Echappe les caracteres speciaux pour SendKeys ( + ^ % ~ ( ) { } [ ] )
function Echapper-SendKeys([string]$texte) {
    return [regex]::Replace($texte, '([+^%~(){}\[\]])', '{$1}')
}

# --- 3. EXPLORATEUR AVEC PLUSIEURS ONGLETS (Windows 11) -----------------

$shellApp = New-Object -ComObject Shell.Application
$fenetresAvant = @($shellApp.Windows() | ForEach-Object { $_.HWND })

# Ouvre la premiere fenetre
Start-Process explorer.exe -ArgumentList "`"$($dossiers[0])`""

# Attend que la nouvelle fenetre apparaisse (max 10 s)
$hwnd = $null
for ($i = 0; $i -lt 20 -and -not $hwnd; $i++) {
    Start-Sleep -Milliseconds 500
    $nouvelle = $shellApp.Windows() |
        Where-Object { $fenetresAvant -notcontains $_.HWND } |
        Select-Object -First 1
    if ($nouvelle) { $hwnd = [IntPtr]$nouvelle.HWND }
}

if ($hwnd) {
    Start-Sleep -Seconds 1
    foreach ($dossier in $dossiers | Select-Object -Skip 1) {
        [Fenetre]::ShowWindow($hwnd, 9) | Out-Null        # restaure si reduite
        [Fenetre]::SetForegroundWindow($hwnd) | Out-Null  # met au premier plan
        Start-Sleep -Milliseconds 400

        [System.Windows.Forms.SendKeys]::SendWait("^t")   # Ctrl+T : nouvel onglet
        Start-Sleep -Milliseconds 800
        [System.Windows.Forms.SendKeys]::SendWait("^l")   # Ctrl+L : barre d'adresse
        Start-Sleep -Milliseconds 300
        [System.Windows.Forms.SendKeys]::SendWait((Echapper-SendKeys $dossier))
        [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
        Start-Sleep -Milliseconds 800
    }
} else {
    # Solution de repli : une fenetre par dossier
    foreach ($dossier in $dossiers | Select-Object -Skip 1) {
        Start-Process explorer.exe -ArgumentList "`"$dossier`""
    }
}

# --- 4. OUTLOOK -----------------------------------------------------------

# Outlook "classique" (Microsoft 365 / Office) :
Start-Process "outlook.exe"

# Si tu utilises le "nouvel Outlook", commente la ligne ci-dessus
# et decommente celle-ci :
# Start-Process "explorer.exe" "shell:AppsFolder\Microsoft.OutlookForWindows_8wekyb3d8bbwe!Microsoft.OutlookforWindows"

# --- 5. AUTRE APPLICATION ------------------------------------------------

if (Test-Path $autreAppli) {
    Start-Process $autreAppli
}
