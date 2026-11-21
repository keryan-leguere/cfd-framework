C----------------------------------------------------------------------
C     AERO_PROBE.INC -- sondes de validation (COMMON /PROBE/)
C
C     Apres chaque lecture de table, AERCAL recopie la valeur
C     interpolee dans VALID_TAB_<TABLE>, avant toute autre operation
C     (increment propulsif, gouvernes, report des moments). Le test de
C     lecture de table (cfd-validation) les lit apres chaque appel via
C     f2py : lib.probe.valid_tab_cx, ...
C
C     Une sonde que l'appel n'a pas atteinte garde sa valeur
C     precedente : l'appelant la remet a zero ou a NaN avant l'appel
C     (VALID_TAB_DCXP n'est ecrite que si IPROPU = 1).
C----------------------------------------------------------------------
      DOUBLE PRECISION VALID_TAB_CX, VALID_TAB_CZ, VALID_TAB_CM
      DOUBLE PRECISION VALID_TAB_CY, VALID_TAB_CL, VALID_TAB_CN
      DOUBLE PRECISION VALID_TAB_DCXP, VALID_TAB_DCMG
      COMMON /PROBE/ VALID_TAB_CX, VALID_TAB_CZ, VALID_TAB_CM,
     &               VALID_TAB_CY, VALID_TAB_CL, VALID_TAB_CN,
     &               VALID_TAB_DCXP, VALID_TAB_DCMG
