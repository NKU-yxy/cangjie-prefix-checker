func q(): Int64 {
    9
}

func r(): Int64 {
    3
}

func sum2(x: Int64, y: Int64): Int64 {
    x + y
}

func prod2(x: Int64, y: Int64): Int64 {
    x * y
}

func okArr(): Array<Int64> {
    Array<Int64>(2, repeat: 0)
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
    let a: Int64 = q()
    let b: Int64 = r()
    println("a=" + (a).toString() + ", b=" + (b).toString())
    println("sum=" + (sum2(a, b)).toString())
    println("prod=" + (prod2(a, b)).toString())
    println("ok=" + (okArr().size).toString())
    println("pad=" + (padGamma(a, b)).toString())
    let bad: Array<Int64> = Array<Int64>("bad")
    println((bad.size).toString())
}
