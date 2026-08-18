func inRange(n: Int64, lo: Int64, hi: Int64): Bool {
    n >= lo && n <= hi
}

func clampHi(n: Int64, hi: Int64): Int64 {
    if (n > hi) {
        hi
    } else {
        n
    }
}

func dist0(n: Int64): Int64 {
    if (n < 0) {
        -n
    } else {
        n
    }
}

func nearTen(n: Int64): Bool {
    dist0(n - 10) < 2
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
    let x: Int64 = 5
    let y: Int64 = clampHi(x, 10)
    println("y=" + (y).toString())
    println("nearTen=" + (nearTen(x)).toString())
    if (inRange(x, 0, 10)) {
        println("in range")
    }
    println("pad=" + (padBeta(x)).toString())
    break
}
