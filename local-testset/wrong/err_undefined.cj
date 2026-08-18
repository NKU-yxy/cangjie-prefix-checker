func bump(k: Int64): Int64 {
    k + 1
}

func double(n: Int64): Int64 {
    n + n
}

func identity(x: Int64): Int64 {
    x
}

func sum3(a: Int64, b: Int64, c: Int64): Int64 {
    a + b + c
}

func min2(a: Int64, b: Int64): Int64 {
    if (a < b) {
        a
    } else {
        b
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
    let x: Int64 = 10
    let y: Int64 = double(x)
    println("bump=" + (bump(x)).toString())
    println("y=" + (y).toString())
    println("id=" + (identity(3)).toString())
    println("sum3=" + (sum3(1, 2, 3)).toString())
    println("min=" + (min2(x, y)).toString())
    println("pad=" + (padBeta(x)).toString())
    let bad: Int64 = accumulator
    println((bad).toString())
}
