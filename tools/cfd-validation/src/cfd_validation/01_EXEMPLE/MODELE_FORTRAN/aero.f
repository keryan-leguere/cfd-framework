! ---------------------------------------------------------------------------
!  aero.f90 - un modele aerodynamique a tables, reduit a l'essentiel.
!
!  C'est le jumeau Fortran du modele factice livre avec cfd-validation
!  (cfd_validation.wrap.factice) : memes tables, memes valeurs, meme
!  convention de rangement.
!
!  Les tables sont rangees en tableaux " longs " : une ligne par point, une
!  colonne par variable, la ou les valeurs tabulees viennent en dernier.
!
!      TAB_CN(i, 1..4) = mach, alpha, delta, CN
!      TAB_CA(i, 1..3) = mach, alpha, CA
!
!  TAB_CN est dimensionne plus large que son remplissage, et NPT_CN dit
!  combien de lignes sont reellement ecrites : c'est la situation courante, et
!  c'est elle que la cle " lignes " de la declaration doit refleter.
!
!  BUG_MODE permet d'injecter volontairement une panne de lecture, pour
!  montrer que le controle la voit. 0 = lecture juste.
! ---------------------------------------------------------------------------

      SUBROUTINE INIT_TABLES()
      IMPLICIT NONE

      INTEGER CAPACITE_CN, CAPACITE_CA
      PARAMETER (CAPACITE_CN = 320)
      PARAMETER (CAPACITE_CA = 42)

      DOUBLE PRECISION TAB_CN(CAPACITE_CN, 4)
      INTEGER NPT_CN
      COMMON /TAB_CN/ TAB_CN, NPT_CN

      DOUBLE PRECISION TAB_CA(CAPACITE_CA, 3)
      INTEGER NPT_CA
      COMMON /TAB_CA/ TAB_CA, NPT_CA

      INTEGER BUG_MODE
      COMMON /REGLAGE/ BUG_MODE

      DOUBLE PRECISION MACH(6), ANGLE(7)
      DOUBLE PRECISION M, A, D
      INTEGER I, J, K, N

      DATA MACH /0.30D0, 0.50D0, 0.70D0, 0.80D0, 0.90D0, 0.95D0/
      DATA ANGLE /-4.0D0, -2.0D0, 0.0D0, 2.0D0, 4.0D0, 6.0D0, 8.0D0/

!     La queue du tableau porte la valeur de remplissage habituelle : ce sont
!     ces lignes-la qu'une declaration sans " lignes " comparerait a tort.
      DO I = 1, CAPACITE_CN
         DO J = 1, 4
            TAB_CN(I, J) = -999.0D0
         END DO
      END DO

      N = 0
      DO I = 1, 6
         DO J = 1, 7
            DO K = 1, 7
               N = N + 1
               M = MACH(I)
               A = ANGLE(J)
               D = ANGLE(K)
               TAB_CN(N, 1) = M
               TAB_CN(N, 2) = A
               TAB_CN(N, 3) = D
               TAB_CN(N, 4) = 0.02D0 + 0.105D0 * A + 0.030D0 * D
     &                      + 0.45D0 * M * M + 0.0012D0 * A * D
            END DO
         END DO
      END DO
      NPT_CN = N

      N = 0
      DO I = 1, 6
         DO J = 1, 7
            N = N + 1
            M = MACH(I)
            A = ANGLE(J)
            TAB_CA(N, 1) = M
            TAB_CA(N, 2) = A
            TAB_CA(N, 3) = 0.021D0 + 0.015D0 * M**4 + 0.00025D0 * A * A
         END DO
      END DO
      NPT_CA = N

      RETURN
      END

! ---------------------------------------------------------------------------
!  EVAL_CN - relit la table CN au point demande.
!
!  BUG_MODE : 0 lecture juste
!             1 facteur d'unite (degres lus comme des radians)
!             2 axes alpha et delta permutes
!             3 indice saturee sur l'axe mach
! ---------------------------------------------------------------------------

      SUBROUTINE EVAL_CN(MACH_IN, ALPHA_IN, DELTA_IN, NPTS, CN_OUT)
      IMPLICIT NONE

      INTEGER NPTS
      DOUBLE PRECISION MACH_IN(NPTS), ALPHA_IN(NPTS), DELTA_IN(NPTS)
      DOUBLE PRECISION CN_OUT(NPTS)
!f2py intent(in) :: MACH_IN, ALPHA_IN, DELTA_IN
!f2py intent(out) :: CN_OUT
!f2py integer intent(hide), depend(MACH_IN) :: NPTS = len(MACH_IN)

      INTEGER CAPACITE_CN
      PARAMETER (CAPACITE_CN = 320)
      DOUBLE PRECISION TAB_CN(CAPACITE_CN, 4)
      INTEGER NPT_CN
      COMMON /TAB_CN/ TAB_CN, NPT_CN

      INTEGER BUG_MODE
      COMMON /REGLAGE/ BUG_MODE

      DOUBLE PRECISION PI, M, A, D, MC
      PARAMETER (PI = 3.141592653589793D0)
      INTEGER I

      DO I = 1, NPTS
         M = MACH_IN(I)
         A = ALPHA_IN(I)
         D = DELTA_IN(I)

         IF (BUG_MODE .EQ. 2) THEN
            MC = A
            A = D
            D = MC
         END IF

         IF (BUG_MODE .EQ. 3) THEN
            IF (M .LE. 0.30D0) M = 0.50D0
            IF (M .GE. 0.95D0) M = 0.90D0
         END IF

         CALL CHERCHER_CN(M, A, D, CN_OUT(I))

         IF (BUG_MODE .EQ. 1) THEN
            CN_OUT(I) = CN_OUT(I) * PI / 180.0D0
         END IF
      END DO

      RETURN
      END

      SUBROUTINE CHERCHER_CN(M, A, D, VALEUR)
      IMPLICIT NONE
      DOUBLE PRECISION M, A, D, VALEUR

      INTEGER CAPACITE_CN
      PARAMETER (CAPACITE_CN = 320)
      DOUBLE PRECISION TAB_CN(CAPACITE_CN, 4)
      INTEGER NPT_CN
      COMMON /TAB_CN/ TAB_CN, NPT_CN

      DOUBLE PRECISION TOL
      PARAMETER (TOL = 1.0D-9)
      INTEGER I

      VALEUR = 0.0D0
      DO I = 1, NPT_CN
         IF (ABS(TAB_CN(I,1) - M) .LT. TOL .AND.
     &       ABS(TAB_CN(I,2) - A) .LT. TOL .AND.
     &       ABS(TAB_CN(I,3) - D) .LT. TOL) THEN
            VALEUR = TAB_CN(I,4)
            RETURN
         END IF
      END DO

      RETURN
      END

! ---------------------------------------------------------------------------
!  EVAL_CA - relit la table CA au point demande. Toujours juste.
! ---------------------------------------------------------------------------

      SUBROUTINE EVAL_CA(MACH_IN, ALPHA_IN, NPTS, CA_OUT)
      IMPLICIT NONE

      INTEGER NPTS
      DOUBLE PRECISION MACH_IN(NPTS), ALPHA_IN(NPTS), CA_OUT(NPTS)
!f2py intent(in) :: MACH_IN, ALPHA_IN
!f2py intent(out) :: CA_OUT
!f2py integer intent(hide), depend(MACH_IN) :: NPTS = len(MACH_IN)

      INTEGER CAPACITE_CA
      PARAMETER (CAPACITE_CA = 42)
      DOUBLE PRECISION TAB_CA(CAPACITE_CA, 3)
      INTEGER NPT_CA
      COMMON /TAB_CA/ TAB_CA, NPT_CA

      DOUBLE PRECISION TOL
      PARAMETER (TOL = 1.0D-9)
      INTEGER I, J

      DO I = 1, NPTS
         CA_OUT(I) = 0.0D0
         DO J = 1, NPT_CA
            IF (ABS(TAB_CA(J,1) - MACH_IN(I)) .LT. TOL .AND.
     &          ABS(TAB_CA(J,2) - ALPHA_IN(I)) .LT. TOL) THEN
               CA_OUT(I) = TAB_CA(J,3)
               GOTO 10
            END IF
         END DO
   10    CONTINUE
      END DO

      RETURN
      END

! ---------------------------------------------------------------------------
!  REGLER_BUG - choisir la panne a injecter. 0 = lecture juste.
! ---------------------------------------------------------------------------

      SUBROUTINE REGLER_BUG(MODE)
      IMPLICIT NONE
      INTEGER MODE
!f2py intent(in) :: MODE
      INTEGER BUG_MODE
      COMMON /REGLAGE/ BUG_MODE
      BUG_MODE = MODE
      RETURN
      END
