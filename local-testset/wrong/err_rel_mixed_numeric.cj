func asFloat(n: Int64): Float64 {
    1.0
}

func asInt(f: Float64): Int64 {
    1
}

func within(n: Int64): Bool {
    n >= 0 && n <= 10
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
    let i: Int64 = 1
    let f: Float64 = asFloat(i)
    println("i=" + (i).toString())
    println("f=" + (f).toString())
    println("within=" + (within(i)).toString())
    println("pad=" + (padBeta(i)).toString())
    let bad: Bool = 1 < 1.0
    println((bad).toString())
}
