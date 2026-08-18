func mod2(n: Int64): Int64 {
    n % 2
}

func half(n: Int64): Int64 {
    n / 2
}

func even(n: Int64): Bool {
    mod2(n) == 0
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
    let n: Int64 = 7
    println("mod2=" + (mod2(n)).toString())
    println("half=" + (half(n)).toString())
    println("even=" + (even(n)).toString())
    println("pad=" + (padAlpha()).toString())
    let bad: Int64 = 1.0 % 2
    println((bad).toString())
}
