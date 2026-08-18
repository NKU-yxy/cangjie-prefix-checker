class Q {
    public static func run<R>(f: () -> R): R {
        f()
    }
}

func tag(): String {
    "Q.run"
}

func z(): Int64 {
    0
}

func one(): Int64 {
    1
}

func two(): Int64 {
    2
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
    println(tag())
    println("z=" + (z()).toString())
    println("one=" + (one()).toString())
    println("two=" + (two()).toString())
    println("pad=" + (padAlpha()).toString())
    let x: Int64 = Q.run({ => "s" })
    println((x).toString())
}
