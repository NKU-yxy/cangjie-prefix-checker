func one(): Int64 {
    1
}

func isZero(n: Int64): Bool {
    n == 0
}

func negate(n: Int64): Int64 {
    -n
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
    let n: Int64 = 42
    println("one=" + (one()).toString())
    println("isZero=" + (isZero(n)).toString())
    println("neg=" + (negate(n)).toString())
    println("pad=" + (padBeta(n)).toString())
    let bad: Bool = !n
    println((bad).toString())
}
