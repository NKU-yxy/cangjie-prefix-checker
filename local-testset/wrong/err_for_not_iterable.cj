func bump(n: Int64): Int64 {
    n + 1
}

func tag(): String {
    "for"
}

func sum3(a: Int64, b: Int64, c: Int64): Int64 {
    a + b + c
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
    let n: Int64 = 42
    println("n=" + (n).toString())
    println("bump=" + (bump(n)).toString())
    println(tag())
    println("sum=" + (sum3(1, 2, 3)).toString())
    println("pad=" + (padAlpha()).toString())
    for (i in n) {
        println((i).toString())
    }
}
