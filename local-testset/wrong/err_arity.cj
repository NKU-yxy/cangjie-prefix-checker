func add(a: Int64, b: Int64): Int64 {
    a + b
}

func zero(): Int64 {
    0
}

func mul(a: Int64, b: Int64): Int64 {
    a * b
}

func clampNonneg(x: Int64): Int64 {
    if (x < 0) {
        0
    } else {
        x
    }
}

func sumPair(a: Int64, b: Int64): Int64 {
    let s: Int64 = a + b
    clampNonneg(s)
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
    let p: Int64 = 3
    let q: Int64 = 4
    println("zero=" + (zero()).toString())
    println("p=" + (p).toString() + ", q=" + (q).toString())
    println("sumPair=" + (sumPair(p, q)).toString())
    println("mul=" + (mul(p, q)).toString())
    println("pad=" + (padBeta(p)).toString())
    let bad: Int64 = add(1)
    println((bad).toString())
}
