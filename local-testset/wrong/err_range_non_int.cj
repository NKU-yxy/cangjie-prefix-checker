func sumRange(lo: Int64, hi: Int64): Int64 {
    var acc: Int64 = 0
    for (i in lo..hi) {
        acc = acc + i
    }
    acc
}

func zero(): Int64 {
    0
}

func ten(): Int64 {
    10
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
    let lo: Int64 = zero()
    let hi: Int64 = ten()
    println("sum=" + (sumRange(lo, hi)).toString())
    println("pad=" + (padGamma(lo, hi)).toString())
    var n: Int64 = 0
    for (i in 0.0..10) {
        n = n + 1
    }
    println((n).toString())
}
