func g(): Int64 {
    7
}

func f(): Int64 {
    true
}

func h(x: Int64): Int64 {
    x + 1
}

func double(x: Int64): Int64 {
    x + x
}

func triple(x: Int64): Int64 {
    x + x + x
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
    let a: Int64 = g()
    println("a=" + (a).toString())
    println("h=" + (h(a)).toString())
    println("dbl=" + (double(a)).toString())
    println("trip=" + (triple(a)).toString())
    println("pad=" + (padBeta(a)).toString())
    println((f()).toString())
}
