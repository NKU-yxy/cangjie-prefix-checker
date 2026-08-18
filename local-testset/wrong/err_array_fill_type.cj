func sizeOf(a: Array<Int64>): Int64 {
    a.size
}

func head(a: Array<Int64>): Int64 {
    a[0]
}

func tail(a: Array<Int64>): Int64 {
    a[a.size - 1]
}

func sumHeadTail(a: Array<Int64>): Int64 {
    head(a) + tail(a)
}

func midIx(a: Array<Int64>): Int64 {
    a.size / 2
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
    let a: Array<Int64> = Array<Int64>(3, repeat: 0)
    println("size=" + (sizeOf(a)).toString())
    println("head=" + (head(a)).toString())
    println("tail=" + (tail(a)).toString())
    println("sumHT=" + (sumHeadTail(a)).toString())
    println("mid=" + (midIx(a)).toString())
    println("pad=" + (padAlpha()).toString())
    a.fill("bad")
    println((a[0]).toString())
}
