func bump(n: Int64): Int64 {
    n + 1
}

func isEven(n: Int64): Bool {
    (n % 2) == 0
}

func sign(n: Int64): Int64 {
    if (n < 0) {
        -1
    } else if (n > 0) {
        1
    } else {
        0
    }
}

func times3(n: Int64): Int64 {
    n * 3
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
    let k: Int64 = 4
    let b: Int64 = bump(k)
    println("b=" + (b).toString())
    println("sign=" + (sign(b)).toString())
    println("t3=" + (times3(k)).toString())
    if (isEven(b)) {
        println("even")
    } else {
        println("odd")
    }
    println("pad=" + (padAlpha()).toString())
    continue
}
