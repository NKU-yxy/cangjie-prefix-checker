func tri<T>(a: T, b: T, c: T, f: (T) -> T): T {
    f(c)
}

func seed(): Int64 {
    0
}

func inc(n: Int64): Int64 {
    n + 1
}

func triple(n: Int64): Int64 {
    n + n + n
}

func bounded(n: Int64): Int64 {
    if (n < 0) {
        0
    } else if (n > 9) {
        9
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
    println("seed=" + (seed()).toString())
    println("inc=" + (inc(2)).toString())
    println("triple=" + (triple(2)).toString())
    println("b=" + (bounded(4)).toString())
    println("pad=" + (padBeta(seed())).toString())
    let out: Int64 = tri(1, 1, "z", { v => v })
    println((out).toString())
}
