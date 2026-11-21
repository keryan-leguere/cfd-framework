C----------------------------------------------------------------------
C     AERO_MODELE.F -- modele aerodynamique factice, deux phases
C
C     Une seule unite de programme, deux points d'entree (ENTRY) :
C
C       CALL AERINI(XREF, YREF, ZREF, LREF, IERR)
C            initialisation : constantes du calcul, controle des tables.
C            A appeler avant tout calcul ; un rappel remplace les
C            constantes precedentes.
C
C       CALL AERCAL(MACH, ALPHA, BETA, XG, YG, ZG, IPROPU, DM, DN,
C                   CX, CY, CZ, CL, CM, CN, IERR)
C            calcul des 6 coefficients en un point de vol.
C
C     Entrees de AERINI
C       XREF, YREF, ZREF  point de reference des moments des tables,
C                         axes corps FRD                         (m)
C       LREF              longueur de reference des moments       (m)
C     Entrees de AERCAL
C       MACH        nombre de Mach                              (-)
C       ALPHA       incidence                                   (deg)
C       BETA        derapage                                    (deg)
C       XG, YG, ZG  centre de gravite, axes corps FRD            (m)
C       IPROPU      0 propulsion eteinte, 1 allumee              (-)
C       DM, DN      braquages de tangage et de lacet             (deg)
C     Sorties de AERCAL
C       CX, CY, CZ  coefficients de force, axes corps FRD
C       CL, CM, CN  coefficients de moment au centre de gravite,
C                   adimensionnes par LREF
C       IERR        0  calcul nominal
C                   1  AERCAL appele avant AERINI    (sorties = 0)
C                   2  point hors des tables : valeurs saturees au
C                      bord, sorties calculees
C                   3  IPROPU ni 0 ni 1               (sorties = 0)
C     Sortie de AERINI
C       IERR        0  initialisation faite
C                   11 grille non strictement croissante
C                   12 longueur de reference <= 0
C
C     Les variables locales en SAVE gardent leur valeur d'un appel a
C     l'autre : c'est ce qui lie les deux phases.
C
C     Les lignes "Cf2py" sont des commentaires pour un compilateur
C     Fortran ; f2py les lit pour savoir quels arguments sont des
C     entrees et lesquels des sorties (fonctions Python rendues :
C     ierr = aerini(xref, yref, zref, lref)
C     cx, cy, cz, cl, cm, cn, ierr = aercal(mach, ..., dn)).
C
C     Sondes de validation : chaque valeur lue dans une table est
C     recopiee dans COMMON /PROBE/ (aero_probe.inc) juste apres sa
C     lecture, sous le nom VALID_TAB_<TABLE>.
C----------------------------------------------------------------------
      SUBROUTINE AERO
      IMPLICIT NONE
      INCLUDE 'aero_dim.inc'
      INCLUDE 'aero_probe.inc'
C
C     Arguments des points d'entree
      INTEGER IERR, IPROPU
      DOUBLE PRECISION XREF, YREF, ZREF, LREF
      DOUBLE PRECISION MACH, ALPHA, BETA, XG, YG, ZG, DM, DN
      DOUBLE PRECISION CX, CY, CZ, CL, CM, CN
C
C     Etat conserve entre les phases
      LOGICAL INIT
      DOUBLE PRECISION SXREF, SYREF, SZREF, ULREF
      SAVE INIT, SXREF, SYREF, SZREF, ULREF
C
C     Locales
      INTEGER IS, ISAT
      DOUBLE PRECISION RX, RY, RZ, DCMG, VG(5)
      DOUBLE PRECISION DEG, ARAD, BRAD, CALFT, ALFT, PHIA
      PARAMETER (DEG = 57.295779513082321D0)
      LOGICAL CROISS
C
C     Fonctions
      DOUBLE PRECISION INTE1D, INTE2D, INTE5D
      EXTERNAL INTE1D, INTE2D, INTE5D
C     Force l'edition de liens du BLOCK DATA (sinon les tables
C     restent a zero quand le modele est pris dans une bibliotheque)
      EXTERNAL AERTBD
C
      DATA INIT / .FALSE. /
      DATA SXREF, SYREF, SZREF, ULREF / 4 * 0.0D0 /
C
C     Appel direct de AERO : sans objet
      WRITE (*, '(A)') ' AERO : appeler AERINI puis AERCAL'
      RETURN
C
C======================================================================
C     Phase 1 : initialisation
C======================================================================
      ENTRY AERINI(XREF, YREF, ZREF, LREF, IERR)
Cf2py intent(in) XREF, YREF, ZREF, LREF
Cf2py intent(out) IERR
C
      INIT = .FALSE.
      IERR = 0
      IF (.NOT. CROISS(TMACH,  NM)) IERR = 11
      IF (.NOT. CROISS(TALPHA, NA)) IERR = 11
      IF (.NOT. CROISS(TBETA,  NB)) IERR = 11
      IF (.NOT. CROISS(TMACHP, NP)) IERR = 11
      IF (IERR .NE. 0) RETURN
      IF (LREF .LE. 0.0D0) THEN
         IERR = 12
         RETURN
      END IF
      SXREF = XREF
      SYREF = YREF
      SZREF = ZREF
      ULREF = 1.0D0 / LREF
      INIT  = .TRUE.
      RETURN
C
C======================================================================
C     Phase 2 : calcul
C======================================================================
      ENTRY AERCAL(MACH, ALPHA, BETA, XG, YG, ZG, IPROPU, DM, DN,
     &             CX, CY, CZ, CL, CM, CN, IERR)
Cf2py intent(in) MACH, ALPHA, BETA, XG, YG, ZG, IPROPU, DM, DN
Cf2py intent(out) CX, CY, CZ, CL, CM, CN, IERR
C
      CX = 0.0D0
      CY = 0.0D0
      CZ = 0.0D0
      CL = 0.0D0
      CM = 0.0D0
      CN = 0.0D0
      IF (.NOT. INIT) THEN
         IERR = 1
         RETURN
      END IF
      IF (IPROPU .NE. 0 .AND. IPROPU .NE. 1) THEN
         IERR = 3
         RETURN
      END IF
C
C     1. Coefficients au point de reference
      ISAT = 0
      CX = INTE2D(TMACH, NM, TALPHA, NA, TCX, NM, MACH, ALPHA, IS)
      VALID_TAB_CX = CX
      ISAT = MAX(ISAT, IS)
      CZ = INTE2D(TMACH, NM, TALPHA, NA, TCZ, NM, MACH, ALPHA, IS)
      VALID_TAB_CZ = CZ
      ISAT = MAX(ISAT, IS)
      CM = INTE2D(TMACH, NM, TALPHA, NA, TCM, NM, MACH, ALPHA, IS)
      VALID_TAB_CM = CM
      ISAT = MAX(ISAT, IS)
      CY = INTE2D(TMACH, NM, TBETA,  NB, TCY, NM, MACH, BETA,  IS)
      VALID_TAB_CY = CY
      ISAT = MAX(ISAT, IS)
      CL = INTE2D(TMACH, NM, TBETA,  NB, TCL, NM, MACH, BETA,  IS)
      VALID_TAB_CL = CL
      ISAT = MAX(ISAT, IS)
      CN = INTE2D(TMACH, NM, TBETA,  NB, TCN, NM, MACH, BETA,  IS)
      VALID_TAB_CN = CN
      ISAT = MAX(ISAT, IS)
C
C     2. Propulsion : increment de CX fonction du Mach seul
      IF (IPROPU .EQ. 1) THEN
         VALID_TAB_DCXP = INTE1D(TMACHP, TDCXP, NP, MACH, IS)
         CX = CX + VALID_TAB_DCXP
         ISAT = MAX(ISAT, IS)
      END IF
C
C     3. Gouvernes : increment de CM tabule en angles polaires
C        cos(alphaT) = cos(alpha) cos(beta)
C        phiA = atan2(sin(beta), sin(alpha) cos(beta))
C        (phiA vaut 0 a alphaT = 0, ou il n'est pas defini : la table
C        doit y etre independante de phiA)
      ARAD = ALPHA / DEG
      BRAD = BETA / DEG
      CALFT = MIN(1.0D0, MAX(-1.0D0, COS(ARAD) * COS(BRAD)))
      ALFT = ACOS(CALFT) * DEG
      PHIA = ATAN2(SIN(BRAD), SIN(ARAD) * COS(BRAD)) * DEG
      VG(1) = MACH
      VG(2) = ALFT
      VG(3) = PHIA
      VG(4) = DM
      VG(5) = DN
      DCMG = INTE5D(TMACHG, NMG, TALFT, NAT, TPHIA, NPH, TDMG, NDM,
     &              TDNG, NDN, TDCMG, VG, IS)
      VALID_TAB_DCMG = DCMG
      ISAT = MAX(ISAT, IS)
      CM = CM + DCMG
C
C     4. Transport des moments du point de reference au CDG :
C        M(G) = M(R) + (R - G) x F, adimensionne par LREF
      RX = (SXREF - XG) * ULREF
      RY = (SYREF - YG) * ULREF
      RZ = (SZREF - ZG) * ULREF
      CL = CL + RY * CZ - RZ * CY
      CM = CM + RZ * CX - RX * CZ
      CN = CN + RX * CY - RY * CX
C
      IERR = 0
      IF (ISAT .NE. 0) IERR = 2
      RETURN
      END
C
C----------------------------------------------------------------------
      LOGICAL FUNCTION CROISS(XT, N)
C
C     Vrai si XT(1..N) est strictement croissante et N >= 2.
C
      IMPLICIT NONE
      INTEGER N
      DOUBLE PRECISION XT(N)
      INTEGER K
C
      CROISS = N .GE. 2
      DO 10 K = 1, N - 1
         IF (XT(K+1) .LE. XT(K)) CROISS = .FALSE.
   10 CONTINUE
      RETURN
      END
