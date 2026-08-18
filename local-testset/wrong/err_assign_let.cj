func triple(n: Int64): Int64 {
    n + n + n
}

func square(n: Int64): Int64 {
    n * n
}

func dec(n: Int64): Int64 {
    n - 1
}

func absDiff(a: Int64, b: Int64): Int64 {
    if (a > b) {
        a - b
    } else {
        b - a
    }
}

func min3(a: Int64, b: Int64, c: Int64): Int64 {
    let m: Int64 = if (a < b) {
        a
    } else {
        b
    }
    if (m < c) {
        m
    } else {
        c
    }
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
    let seed: Int64 = 2
    println("triple(seed)=" + (triple(seed)).toString())
    println("square(seed)=" + (square(seed)).toString())
    let a: Int64 = 5
    let b: Int64 = dec(a)
    println("b=" + (b).toString())
    println("diff=" + (absDiff(a, b)).toString())
    println("min3=" + (min3(a, b, 0)).toString())
    let n: Int64 = 1
    n = "x"
    println("n=" + (n).toString())
    println("pad=" + (padGamma(seed, a)).toString())
}
