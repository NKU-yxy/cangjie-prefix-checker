func one(): Int64 {
    1
}

func loopCount(n: Int64): Int64 {
    var c: Int64 = 0
    var i: Int64 = 0
    while (i < n) {
        c = c + 1
        i = i + 1
    }
    c
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
    let n: Int64 = 3
    println("one=" + (one()).toString())
    println("count=" + (loopCount(n)).toString())
    println("pad=" + (padBeta(n)).toString())
    var x: Int64 = 0
    while (1) {
        x = x + 1
        if (x > 2) {
            break
        }
    }
    println((x).toString())
}
