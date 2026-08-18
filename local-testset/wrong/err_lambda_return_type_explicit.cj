func g(f: (Int64) -> Int64): Int64 {
    f(0)
}

func seed(): Int64 {
    0
}

func add1(n: Int64): Int64 {
    n + 1
}

func mul2(n: Int64): Int64 {
    n * 2
}

func neg(n: Int64): Int64 {
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
    println("seed=" + (seed()).toString())
    println("add1=" + (add1(4)).toString())
    println("mul2=" + (mul2(3)).toString())
    println("neg=" + (neg(1)).toString())
    println("pad=" + (padBeta(seed())).toString())
    let bad: Int64 = g({ v: Int64 => "no" })
    println((bad).toString())
}
