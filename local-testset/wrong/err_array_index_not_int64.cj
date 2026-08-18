func sum2(x: Int64, y: Int64): Int64 {
    x + y
}

func firstOf(a: Array<Int64>): Int64 {
    a[0]
}

func lastOf(a: Array<Int64>): Int64 {
    a[a.size - 1]
}

func span(a: Array<Int64>): Int64 {
    lastOf(a) - firstOf(a)
}

func product(a: Array<Int64>): Int64 {
    a[0] * a[1]
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
    let a: Array<Int64> = [1, 2]
    let u: Int64 = sum2(a[0], a[1])
    println("u=" + (u).toString())
    println("first=" + (firstOf(a)).toString())
    println("last=" + (lastOf(a)).toString())
    println("span=" + (span(a)).toString())
    println("prod=" + (product(a)).toString())
    println("pad=" + (padBeta(u)).toString())
    let bad: Int64 = a[true]
    println((bad).toString())
}
