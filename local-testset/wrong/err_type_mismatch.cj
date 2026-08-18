func alwaysOne(): Int64 {
    1
}

func twice(n: Int64): Int64 {
    n + n
}

func isPos(n: Int64): Bool {
    n > 0
}

func absv(n: Int64): Int64 {
    if (n < 0) {
        -n
    } else {
        n
    }
}

func half(n: Int64): Int64 {
    n / 2
}

func padAlpha(): Int64 {
    1
}

func padBeta(n: Int64): Int64 {
    n + padAlpha()
}

func padGamma(a: Int64, b: Int64): Int64 {
    a + b
}

func padDelta(s: String): String {
    s
}

func padEpsilon(flag: Bool): Bool {
    flag
}

func padZeta(a: Int64, b: Int64, c: Int64): Int64 {
    a + b + c
}

func padEta(n: Int64): Int64 {
    if (n < 0) {
        0
    } else {
        n
    }
}

main(): Unit {
    let ok: Int64 = alwaysOne()
    println("ok=" + (ok).toString())
    let t: Int64 = twice(ok)
    println("t=" + (t).toString())
    println("pos=" + (isPos(t)).toString())
    println("abs=" + (absv(-2)).toString())
    println("half=" + (half(t)).toString())
    println("pad=" + (padGamma(ok, t)).toString())
    let flag: Int64 = true
    println("flag=" + (flag).toString())
}
