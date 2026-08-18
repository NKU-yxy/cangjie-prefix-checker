import std.collection.*

func keyCount(): Int64 {
    1
}

func bump(n: Int64): Int64 {
    n + 1
}

func double(n: Int64): Int64 {
    n + n
}

func tagMap(): String {
    "map"
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
    let m: HashMap<String, Int64> = HashMap<String, Int64>([("a", 1)])
    println("keys~=" + (keyCount()).toString())
    println("bump=" + (bump(0)).toString())
    println("tag=" + (tagMap()).toString())
    println("dbl=" + (double(3)).toString())
    println("pad=" + (padAlpha()).toString())
    for (x in m) {
        println((x).toString())
    }
}
