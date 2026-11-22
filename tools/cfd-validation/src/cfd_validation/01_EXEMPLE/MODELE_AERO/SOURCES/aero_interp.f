C----------------------------------------------------------------------
C     AERO_INTERP.F -- interpolation lineaire 1D, bilineaire 2D et
C     multilineaire 5D, avec une consigne hors grille PAR AXE :
C
C       IEXT = ISATU (0) : saturation, la valeur au bord de la grille ;
C       IEXT = IEXTR (1) : extrapolation lineaire, prolongement de la
C                          derniere maille (poids T < 0 ou T > 1).
C
C     Dans les deux cas, un point hors grille leve ISAT = 1 (IERR = 2
C     dans AERCAL) : le calcul se fait, l'appelant est prevenu.
C
C     Forme (1-T)*V(I) + T*V(I+1) : sur un noeud (T = 0 ou T = 1) le
C     resultat est la valeur de la table au bit pres ; hors grille, la
C     meme formule extrapole.
C----------------------------------------------------------------------
      SUBROUTINE CHERCH(XT, N, X, IEXT, I, T, ISAT)
C
C     Cherche I dans [1, N-1] et le poids T tels que
C     X = (1-T)*XT(I) + T*XT(I+1). Dans la grille, T est dans [0, 1].
C     Hors grille, I est la maille du bord et T vaut 0 ou 1 (IEXT =
C     ISATU) ou sort de [0, 1] (IEXT = IEXTR).
C     XT strictement croissante (verifie par AERINI), N >= 2.
C
      IMPLICIT NONE
      INTEGER N, IEXT, I, ISAT
      DOUBLE PRECISION XT(N), X, T
      INTEGER K
C
      ISAT = 0
      IF (X .LT. XT(1)) THEN
         ISAT = 1
         I = 1
         IF (IEXT .EQ. 1) THEN
            T = (X - XT(1)) / (XT(2) - XT(1))
         ELSE
            T = 0.0D0
         END IF
         RETURN
      END IF
      IF (X .GE. XT(N)) THEN
         I = N - 1
         T = 1.0D0
         IF (X .GT. XT(N)) THEN
            ISAT = 1
            IF (IEXT .EQ. 1) T = (X - XT(N-1)) / (XT(N) - XT(N-1))
         END IF
         RETURN
      END IF
      DO 10 K = 1, N - 1
         IF (X .LT. XT(K+1)) THEN
            I = K
            GO TO 20
         END IF
   10 CONTINUE
      I = N - 1
   20 CONTINUE
      T = (X - XT(I)) / (XT(I+1) - XT(I))
      RETURN
      END
C
C----------------------------------------------------------------------
      DOUBLE PRECISION FUNCTION INTE1D(XT, VT, N, X, IEXT, ISAT)
C
C     Interpolation lineaire de VT(XT) en X ; IEXT : consigne hors grille.
C
      IMPLICIT NONE
      INTEGER N, IEXT, ISAT
      DOUBLE PRECISION XT(N), VT(N), X
      INTEGER I
      DOUBLE PRECISION T
C
      CALL CHERCH(XT, N, X, IEXT, I, T, ISAT)
      INTE1D = (1.0D0 - T) * VT(I) + T * VT(I+1)
      RETURN
      END
C
C----------------------------------------------------------------------
      DOUBLE PRECISION FUNCTION INTE2D(XT, NX, IEX, YT, NY, IEY,
     &                                 TAB, LD, X, Y, ISAT)
C
C     Interpolation bilineaire de TAB(XT, YT) en (X, Y).
C     TAB(LD, *) : premier indice selon XT, second selon YT.
C     IEX, IEY : consigne hors grille de chaque axe.
C
      IMPLICIT NONE
      INTEGER NX, IEX, NY, IEY, LD, ISAT
      DOUBLE PRECISION XT(NX), YT(NY), TAB(LD,*), X, Y
      INTEGER I, J, ISX, ISY
      DOUBLE PRECISION T, U
C
      CALL CHERCH(XT, NX, X, IEX, I, T, ISX)
      CALL CHERCH(YT, NY, Y, IEY, J, U, ISY)
      ISAT = MAX(ISX, ISY)
      INTE2D = (1.0D0 - T) * (1.0D0 - U) * TAB(I,   J)
     &       +          T  * (1.0D0 - U) * TAB(I+1, J)
     &       + (1.0D0 - T) *          U  * TAB(I,   J+1)
     &       +          T  *          U  * TAB(I+1, J+1)
      RETURN
      END
C
C----------------------------------------------------------------------
      DOUBLE PRECISION FUNCTION INTE5D(X1, N1, X2, N2, X3, N3, X4, N4,
     &                                 X5, N5, IEXT, TAB, V, ISAT)
C
C     Interpolation multilineaire de TAB(X1, X2, X3, X4, X5) au point
C     V(1..5) : somme sur les 32 coins de la maille, chaque coin pese
C     le produit des poids (1-T) ou T de ses cinq axes. Sur un noeud,
C     les poids valent exactement 0 ou 1 : valeur de la table au bit
C     pres. TAB(N1,N2,N3,N4,N5), premier indice selon X1.
C     IEXT(1..5) : consigne hors grille de chaque axe.
C
      IMPLICIT NONE
      INTEGER N1, N2, N3, N4, N5, IEXT(5), ISAT
      DOUBLE PRECISION X1(N1), X2(N2), X3(N3), X4(N4), X5(N5)
      DOUBLE PRECISION TAB(N1,N2,N3,N4,N5), V(5)
      INTEGER IB(5), IS(5), K, D, IC(5)
      DOUBLE PRECISION T(5), P, S
C
      CALL CHERCH(X1, N1, V(1), IEXT(1), IB(1), T(1), IS(1))
      CALL CHERCH(X2, N2, V(2), IEXT(2), IB(2), T(2), IS(2))
      CALL CHERCH(X3, N3, V(3), IEXT(3), IB(3), T(3), IS(3))
      CALL CHERCH(X4, N4, V(4), IEXT(4), IB(4), T(4), IS(4))
      CALL CHERCH(X5, N5, V(5), IEXT(5), IB(5), T(5), IS(5))
      ISAT = MAX(IS(1), IS(2), IS(3), IS(4), IS(5))
C
      S = 0.0D0
      DO 20 K = 0, 31
         P = 1.0D0
         DO 10 D = 1, 5
            IF (MOD(K / 2**(D-1), 2) .EQ. 1) THEN
               IC(D) = IB(D) + 1
               P = P * T(D)
            ELSE
               IC(D) = IB(D)
               P = P * (1.0D0 - T(D))
            END IF
   10    CONTINUE
         S = S + P * TAB(IC(1), IC(2), IC(3), IC(4), IC(5))
   20 CONTINUE
      INTE5D = S
      RETURN
      END
