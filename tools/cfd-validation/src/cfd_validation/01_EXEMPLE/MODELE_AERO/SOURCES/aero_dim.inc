C----------------------------------------------------------------------
C     AERO_DIM.INC -- dimensions et COMMON des tables du modele aero
C
C     Inclus par AERO (aero_modele.f) et le BLOCK DATA AERTBD
C     (aero_tables.f) : seule declaration du COMMON.
C
C     NM : points en Mach        NA : points en incidence (alpha)
C     NB : points en derapage    NP : points en Mach de la propulsion
C     NAR : points en incidence de TDCZR (radians)
C     NBA : points en |derapage| de TDCXB
C     Les tables des coefficients sont carrees : NM = NA = NB.
C     Table 5D des gouvernes : NMG x NAT x NPH x NDM x NDN (carree).
C----------------------------------------------------------------------
      INTEGER NM, NA, NB, NP
      PARAMETER (NM = 7, NA = 7, NB = 7, NP = 7)
      INTEGER NAR, NBA
      PARAMETER (NAR = 7, NBA = 7)
      INTEGER NMG, NAT, NPH, NDM, NDN
      PARAMETER (NMG = 5, NAT = 5, NPH = 5, NDM = 5, NDN = 5)
C
C     Consigne hors grille d'un axe (CHERCH) : saturation au bord, ou
C     extrapolation lineaire de la derniere maille
      INTEGER ISATU, IEXTR
      PARAMETER (ISATU = 0, IEXTR = 1)
C
C     Grilles (Mach, degres)
      DOUBLE PRECISION TMACH(NM), TALPHA(NA), TBETA(NB), TMACHP(NP)
C     Coefficients au point de reference, axes corps FRD
      DOUBLE PRECISION TCX(NM,NA), TCZ(NM,NA), TCM(NM,NA)
      DOUBLE PRECISION TCY(NM,NB), TCL(NM,NB), TCN(NM,NB)
C     Propulsion : increment de CX, fonction du Mach seul
      DOUBLE PRECISION TDCXP(NP)
C     Increment de CZ de la voilure : grille d'incidence en RADIANS
C     (table reprise d'un autre code ; AERCAL recoit ALPHA en degres)
      DOUBLE PRECISION TALFR(NAR), TDCZR(NM,NAR)
C     Increment de CX en derapage, tabule en |beta| (degres, >= 0)
      DOUBLE PRECISION TABETA(NBA), TDCXB(NM,NBA)
C
      COMMON /AERTAB/ TMACH, TALPHA, TBETA, TMACHP,
     &                TCX, TCZ, TCM, TCY, TCL, TCN, TDCXP,
     &                TALFR, TDCZR, TABETA, TDCXB
C
C     Gouvernes : grilles (Mach, degres) et increment de CM
      DOUBLE PRECISION TMACHG(NMG), TALFT(NAT), TPHIA(NPH)
      DOUBLE PRECISION TDMG(NDM), TDNG(NDN)
      DOUBLE PRECISION TDCMG(NMG,NAT,NPH,NDM,NDN)
      COMMON /AERTB5/ TMACHG, TALFT, TPHIA, TDMG, TDNG, TDCMG
