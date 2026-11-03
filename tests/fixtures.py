"""Backwards-compatible re-export of the eval gold labels.

The gold moved to ptl.eval.gold so the shipped CLI can load it;
imports of tests.fixtures keep working unchanged.
"""
from ptl.eval.gold import (  # noqa: F401
    SEEDS,
    S1_GOLDEN,
    S1_CAFE_AMAZON,
    S2_LOTUS,
    S3_JONES,
    S4_STARBUCKS,
    S5_SEVEN,
    S6_ETOILE,
    S7_CPAXTRA_6662,
    S8_JAYTO_SEAFOOD,
    S9_DQ_JPARK,
    S10_TSURUHA_JPARK,
    S11_PABOON_CAFE3,
    S12_SBUX_ESPLANADE2,
    S13_WATSONS_ESPLANADE,
    S14_JONES_DELIVERY,
    S15_TOPS_ESPLANADE,
    S16_SEVEN_02304B,
    S17_ZAABOLE_ISAAN,
    S18_PUNGSIAM_FPARK,
    S19_WATSONS_RATCHADA,
    S20_MRDIY_STREET,
    S21_RADNA,
    S22_SEVEN2,
    S23_OASIS,
    S24_SNOWTEE_HK,
    S25_ZAABONLY_ISAAN,
    fresh,
    fresh_seed,
)
