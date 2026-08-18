func seed(): Int64 {
    11
}

func inc(n: Int64): Int64 {
    n + 1
}

func dec(n: Int64): Int64 {
    n - 1
}

func pairDup(a: Int64, a: Int64): Int64 {
    a + a
}

func double(n: Int64): Int64 {
    n + n
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
    let base: Int64 = seed()
    println("base=" + (base).toString())
    let t: Int64 = inc(base)
    println("t=" + (t).toString())
    println("dec=" + (dec(t)).toString())
    println("dbl=" + (double(base)).toString())
    println("pair=" + (pairDup(1, 2)).toString())
    println("pad=" + (padGamma(base, t)).toString())
}
