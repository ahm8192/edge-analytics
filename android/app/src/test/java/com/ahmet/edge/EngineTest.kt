package com.ahmet.edge

import com.ahmet.edge.domain.engine.*
import org.junit.Assert.*
import org.junit.Test

class EngineTest {

    @Test fun `skor matrisi 1'e toplanir`() {
        val m = PoissonMath.scoreMatrix(1.5, 1.1, -0.03)
        val total = m.sumOf { it.sum() }
        assertEquals(1.0, total, 1e-9)
    }

    @Test fun `1X2 olasiliklari 1'e toplanir`() {
        val m = PoissonMath.scoreMatrix(1.6, 1.2, -0.05)
        assertEquals(1.0, Markets.oneXtwo(m).values.sum(), 1e-9)
    }

    @Test fun `devig marji kaldirir`() {
        val prices = listOf(2.10, 3.40, 3.60)
        assertTrue(Devig.marginPct(prices) > 0)
        listOf(Devig.multiplicative(prices), Devig.power(prices), Devig.shin(prices))
            .forEach { assertEquals(1.0, it.sum(), 1e-6) }
    }

    @Test fun `shin favoriye multiplicative'den farkli agirlik verir`() {
        val prices = listOf(1.30, 5.50, 11.0)
        val mult = Devig.multiplicative(prices)
        val shin = Devig.shin(prices)
        // Longshot bias düzeltmesi: uzun ihtimalin olasılığı düşmeli
        assertTrue(shin.last() < mult.last())
    }

    @Test fun `kenar yoksa kelly sifir`() {
        assertEquals(0.0, Kelly.fraction(0.40, 2.0), 1e-9)
    }

    @Test fun `kelly kasa limitini asamaz`() {
        val r = Kelly.stake(prob = 0.90, price = 3.0, bankroll = 10_000.0)
        assertTrue(r.pctBankroll <= 0.0201)
        assertEquals("kasa limiti (%2)", r.cappedBy)
    }

    @Test fun `martingale uyarisi kayip serisinde tetiklenir`() {
        val w = Kelly.martingaleWarning(listOf("lose", "lose", "lose"), 300.0, 100.0)
        assertNotNull(w)
    }

    @Test fun `deger olmayan secim isaretlenmez`() {
        val model = mapOf("HOME" to 0.45, "DRAW" to 0.27, "AWAY" to 0.28)
        val book = mapOf("HOME" to 2.05, "DRAW" to 3.50, "AWAY" to 3.40)
        val res = Edge.compute(model, book)
        assertTrue(res.none { it.isValue && it.edgePct < Edge.MIN_EDGE })
    }
}
