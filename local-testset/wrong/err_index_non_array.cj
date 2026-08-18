func bump(n: Int64): Int64 {
    n + 1
}

func double(n: Int64): Int64 {
    n + n
}

func zero(): Int64 {
    0
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
    let n: Int64 = 0
    println("n=" + (n).toString())
    println("bump=" + (bump(n)).toString())
    println("dbl=" + (double(n)).toString())
    println("zero=" + (zero()).toString())
    println("pad=" + (padBeta(n)).toString())
    let bad: Int64 = n[0]
    println((bad).toString())
}
