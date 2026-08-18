func bad<T>(a: T, b: T, f: (T) -> T): T {
    f(a)
}

func one(): Int64 {
    1
}

func letter(): String {
    "x"
}

func pairInts(): Array<Int64> {
    [1, 2]
}

func sumPair(a: Array<Int64>): Int64 {
    a[0] + a[1]
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
    println("one=" + (one()).toString())
    println(letter())
    println("pair=" + (pairInts().size).toString())
    println("sumPair=" + (sumPair(pairInts())).toString())
    println("pad=" + (padAlpha()).toString())
    let out: Int64 = bad(1, "x", { v: Int64 => v })
    println((out).toString())
}
