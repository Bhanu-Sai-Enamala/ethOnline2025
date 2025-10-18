;; ============================================================
;; rebalance_rules.metta
;; Dynamic risk-to-weight mapping for USDC/USDT rebalancing
;; Works with Python agent query: (target-weight-adjusted USDC ?w)
;; ============================================================

;; -----------
;; Basic helpers
;; -----------
(:- (abs ?x ?ax)
    (if (> ?x 0.0)
        (= ?ax ?x)
        (= ?ax (- 0.0 ?x))))

(:- (clamp ?x ?lo ?hi ?y)
    (if (< ?x ?lo)
        (= ?y ?lo)
        (if (> ?x ?hi)
            (= ?y ?hi)
            (= ?y ?x))))

;; -----------
;; Combine peg + sentiment risks
;; -----------
(:- (combined-risk USDC ?r)
    (peg-risk USDC ?rp)
    (sentiment-risk USDC ?rs)
    (abs ?rs ?rsa)
    (= ?r (+ (* 0.7 ?rp) (* 0.3 ?rsa))))

(:- (combined-risk USDT ?r)
    (peg-risk USDT ?rp)
    (sentiment-risk USDT ?rs)
    (abs ?rs ?rsa)
    (= ?r (+ (* 0.7 ?rp) (* 0.3 ?rsa))))

;; -----------
;; Liquidity gate (true if |1 - quote| > 0.003)
;; -----------
(:- (liq-gate true)
    (liq-quote ?q)
    (= ?d (- 1.0 ?q))
    (abs ?d ?ad)
    (> ?ad 0.003))

(:- (liq-gate false)
    (or (not (liq-quote ?q)) true)
    true)

;; -----------
;; Regime calculation
;; -----------
(:- (regime RED)
    (combined-risk USDC ?ru)
    (combined-risk USDT ?rt)
    (if (> ?ru ?rt)
        (= ?max ?ru)
        (= ?max ?rt))
    (> ?max 0.60))

(:- (regime YELLOW)
    (combined-risk USDC ?ru)
    (combined-risk USDT ?rt)
    (if (> ?ru ?rt)
        (= ?max ?ru)
        (= ?max ?rt))
    (<= ?max 0.60)
    (> ?max 0.35))

(:- (regime GREEN)
    (combined-risk USDC ?ru)
    (combined-risk USDT ?rt)
    (if (> ?ru ?rt)
        (= ?max ?ru)
        (= ?max ?rt))
    (<= ?max 0.35))

;; -----------
;; Target weight core logic
;; base 0.50, max tilt 0.10 toward lower-risk coin
;; liquidity gate halves tilt
;; -----------
(:- (target-weight-adjusted USDC ?w)
    (combined-risk USDC ?ru)
    (combined-risk USDT ?rt)
    (= ?tilt (* 0.10 (- ?rt ?ru)))   ;; positive tilt → favor USDC
    (if (liq-gate true)
        (= ?tilt_adj (* 0.5 ?tilt))
        (= ?tilt_adj ?tilt))
    (= ?raw (+ 0.50 ?tilt_adj))
    (clamp ?raw 0.20 0.80 ?w)
    (rationale (string "MeTTa tilt rule; risks=" ?ru "," ?rt)))

;; ----------------
;; Sanity print hook (for debugging)
;; ----------------
!(println "✅ MeTTa rule executed for USDC weighting")