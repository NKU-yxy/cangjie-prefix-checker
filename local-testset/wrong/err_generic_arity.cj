func id<T>(x: T): T {
    x
}

func bump(n: Int64): Int64 {
    n + 1
}

func double(n: Int64): Int64 {
    n + n
}

func triple(n: Int64): Int64 {
    n + n + n
}

func clampSmall(n: Int64): Int64 {
    if (n > 100) {
        100
    } else {
        n
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
    let a: Int64 = bump(0)
    println("a=" + (a).toString())
    println("d=" + (double(a)).toString())
    println("t=" + (triple(a)).toString())
    println("c=" + (clampSmall(a)).toString())
    println("pad=" + (padBeta(a)).toString())
    let bad: Int64 = id<Int64, Int64>(1)
    println((bad).toString())
}
