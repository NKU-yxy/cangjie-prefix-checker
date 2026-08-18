func mk(): Array<Int64> {
    Array<Int64>(2, repeat: 0)
}

func head(a: Array<Int64>): Int64 {
    a[0]
}

func tail(a: Array<Int64>): Int64 {
    a[1]
}

func sum2(a: Array<Int64>): Int64 {
    head(a) + tail(a)
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
    let a: Array<Int64> = mk()
    println("head=" + (head(a)).toString())
    println("tail=" + (tail(a)).toString())
    println("sum=" + (sum2(a)).toString())
    println("pad=" + (padAlpha()).toString())
    let bad: Array<Int64> = Array<Int64>(3, rept: 1)
    println((bad[0]).toString())
}
